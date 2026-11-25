/* SPDX-License-Identifier: MIT
 * Open Audio Bridge: original, optional adaptive stereo tone and width.
 * No dynamic allocation, file access, or locks in the audio callback.
 * This is a stereo enhancement, not a spatial/object-audio implementation.
 */
#include "mini_ladspa.h"
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define PI 3.14159265358979323846

enum { IN_L, IN_R, OUT_L, OUT_R, MODE, WIDTH, PORTS };

typedef struct {
    LADSPA_Data *port[PORTS];
    double low_coeff, high_coeff, side_coeff;
    double energy_coeff, tone_coeff, off_coeff, width_coeff;
    double low_state[2], high_state[2], side_state;
    double energy[3];
    double bass_gain, treble_gain, width;
} Music;

static double time_coefficient(unsigned long rate, double seconds) {
    return -expm1(-1.0 / (rate * seconds));
}

/* First-order topology-preserving transform. The low-pass and its
 * complement sum precisely to the original signal and use stable states. */
static double filter_coefficient(unsigned long rate, double frequency) {
    const double t = tan(PI * frequency / rate);
    return t / (1.0 + t);
}

static double lowpass(double input, double coefficient, double *state) {
    const double v = (input - *state) * coefficient;
    const double output = v + *state;
    const double next = output + v;
    *state = fabs(next) < 1.e-24 ? 0.0 : next;
    return output;
}

static double smoothstep(double x) {
    x = fmin(fmax(x, 0.0), 1.0);
    return x * x * (3.0 - 2.0 * x);
}

static double control(const LADSPA_Data *port, double upper) {
    if (!port || !isfinite(*port)) return 0.0;
    return fmin(fmax(*port, 0.0), upper);
}

static float finite_sample(double sample) {
    /* No normal audio is clipped here. Keep pathological floating-point input
     * from producing infinity at this plugin's output. Final peak protection
     * is deliberately delegated to the downstream gain plugin. */
    if (!isfinite(sample)) return 0.0f;
    return (float)fmin(fmax(sample, -FLT_MAX), FLT_MAX);
}

static LADSPA_Handle create(const LADSPA_Descriptor *descriptor, unsigned long rate) {
    (void)descriptor;
    if (rate < 8000 || rate > 768000) return NULL;
    Music *music = calloc(1, sizeof(*music));
    if (!music) return NULL;
    music->low_coeff = filter_coefficient(rate, 180.0);
    music->high_coeff = filter_coefficient(rate, 3000.0);
    music->side_coeff = filter_coefficient(rate, 700.0);
    music->energy_coeff = time_coefficient(rate, 3.0);
    music->tone_coeff = time_coefficient(rate, 0.6);
    music->off_coeff = time_coefficient(rate, 0.035);
    music->width_coeff = time_coefficient(rate, 0.035);
    return music;
}

static void connect(LADSPA_Handle handle, unsigned long port, LADSPA_Data *data) {
    Music *music = handle;
    if (music && port < PORTS) music->port[port] = data;
}

static void activate(LADSPA_Handle handle) {
    Music *music = handle;
    if (!music) return;
    memset(music->low_state, 0, sizeof(music->low_state));
    memset(music->high_state, 0, sizeof(music->high_state));
    memset(music->energy, 0, sizeof(music->energy));
    music->side_state = 0.0;
    music->bass_gain = music->treble_gain = music->width = 0.0;
}

static void run(LADSPA_Handle handle, unsigned long samples) {
    Music *music = handle;
    if (!music || !music->port[IN_L] || !music->port[IN_R] ||
        !music->port[OUT_L] || !music->port[OUT_R]) return;
    const int mode = (int)(control(music->port[MODE], 2.0) + 0.5);
    const double width_target = control(music->port[WIDTH], 25.0) / 100.0;
    /* Positive-only bounded contributions (gain minus 1). Warm has at most
     * +2.5 dB bass / +1.4 dB high, Electronic +3.2 dB / +2.5 dB. Even
     * bass-rich or bright material retains a small lift, never an EQ cut. */
    const double bass_min = mode == 2 ? 0.07 : 0.05;
    const double bass_max = mode == 2 ? 0.44544 : 0.33352;
    const double high_min = mode == 2 ? 0.035 : 0.02;
    const double high_max = mode == 2 ? 0.33352 : 0.17490;
    const double gain_coeff = mode ? music->tone_coeff : music->off_coeff;
    for (unsigned long sample = 0; sample < samples; ++sample) {
        double input[2], low[2], mid[2], high[2];
        double power[3] = {0.0, 0.0, 0.0};
        for (int c = 0; c < 2; ++c) {
            const float value = music->port[IN_L + c][sample];
            input[c] = isfinite(value) ? value : 0.0;
            low[c] = lowpass(input[c], music->low_coeff, &music->low_state[c]);
            const double below_high = lowpass(input[c], music->high_coeff, &music->high_state[c]);
            high[c] = input[c] - below_high;
            mid[c] = below_high - low[c];
            power[0] += low[c] * low[c] * 0.5;
            power[1] += mid[c] * mid[c] * 0.5;
            power[2] += high[c] * high[c] * 0.5;
        }
        for (int band = 0; band < 3; ++band) {
            music->energy[band] += music->energy_coeff * (power[band] - music->energy[band]);
            if (music->energy[band] < 1.e-36) music->energy[band] = 0.0;
        }
        /* Normalized spectral measures keep the enhancement independent of
         * listening level, and the slow energy average avoids per-beat gain
         * changes. The gain is common to both channels, preserving balance. */
        const double total = music->energy[0] + music->energy[1] + music->energy[2];
        const double bass_share = total > 1.e-16 ? music->energy[0] / total : 0.0;
        const double high_share = total > 1.e-16 ? music->energy[2] / total : 0.0;
        const double bass_need = smoothstep((0.55 - bass_share) / 0.50);
        const double high_need = smoothstep((0.55 - high_share) / 0.50);
        const double bass_target = mode ? bass_min + (bass_max - bass_min) * bass_need : 0.0;
        const double high_target = mode ? high_min + (high_max - high_min) * high_need : 0.0;
        music->bass_gain += gain_coeff * (bass_target - music->bass_gain);
        music->treble_gain += gain_coeff * (high_target - music->treble_gain);
        music->width += music->width_coeff * (width_target - music->width);
        if (!mode && music->bass_gain < 1.e-7) music->bass_gain = 0.0;
        if (!mode && music->treble_gain < 1.e-7) music->treble_gain = 0.0;
        if (width_target == 0.0 && music->width < 1.e-7) music->width = 0.0;
        /* Add only the complementary low and high components to the original
         * audio. No reconstructed signal or filter coloration in bypass. */
        const double left = input[0] + music->bass_gain * low[0] + music->treble_gain * high[0];
        const double right = input[1] + music->bass_gain * low[1] + music->treble_gain * high[1];
        const double side = (left - right) * 0.5;
        const double side_low = lowpass(side, music->side_coeff, &music->side_state);
        /* Add equal-and-opposite upper-side components only. Center and
         * stereo sum are unchanged; a mono input never creates new width. */
        const double widened = music->width * (side - side_low);
        if (music->bass_gain == 0.0 && music->treble_gain == 0.0 && music->width == 0.0) {
            /* Preserve the exact finite input (including signed zero) once
             * the bypass transition has settled; filters stay warm. */
            music->port[OUT_L][sample] = (float)input[0];
            music->port[OUT_R][sample] = (float)input[1];
        } else {
            music->port[OUT_L][sample] = finite_sample(left + widened);
            music->port[OUT_R][sample] = finite_sample(right - widened);
        }
    }
}

static void cleanup(LADSPA_Handle handle) { free(handle); }
static const LADSPA_PortDescriptor ports[PORTS] = {9, 9, 10, 10, 5, 5};
static const char *const names[PORTS] = {
    "Input L", "Input R", "Output L", "Output R", "Mode", "Width (%)"
};
static const LADSPA_PortRangeHint hints[PORTS] = {
    {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {3, 0, 2}, {3, 0, 25}
};
static const LADSPA_Descriptor descriptor = {
    795418, "oab_music_enhance", LADSPA_PROPERTY_HARD_RT_CAPABLE,
    "Open Audio Bridge adaptive stereo enhancement", "Open Audio Bridge project", "MIT",
    PORTS, ports, names, hints, NULL, create, connect, activate, run, NULL, NULL, NULL, cleanup
};
const LADSPA_Descriptor *ladspa_descriptor(unsigned long index) {
    return index == 0 ? &descriptor : NULL;
}
