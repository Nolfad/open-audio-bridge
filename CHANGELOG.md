# 0.3.0 — 23/11/2026

- Processamento dentro das saídas reais do PipeWire, sem dispositivo virtual ou segundo controle de volume.
- “Padrão do sistema” acompanha a seleção do KDE; saída fixa opcional restringe o efeito sem forçar o destino dos aplicativos.
- Janela controla o mesmo volume e mudo do KDE. Bandeja opcional, desativada por padrão.
- Preserva equalização, dinâmica, curva +20 pontos e proteção final de picos em −4 dBFS.
- Migração reversível das versões anteriores, com cópias de segurança; perfis de reprodução privados preservam os controles do microfone.
- Exige PipeWire 1.6+ e WirePlumber 0.5.15+. Validado com HyperX USB e HDMI no Tuxedo OS. Saídas surround e volume Bluetooth por hardware ainda não são suportados.

# 0.2.3 — 22/11/2026

- Curva corrigida conforme a intenção esclarecida: +20 pontos percentuais, não multiplicação por dois. 80% → antigos 100%; 100% → antigos 120%.
- Entrada gradual do reforço entre 0% e 20%, preservando silêncio e continuidade.
- Migração das duas curvas anteriores preserva o nível quando alcançável; níveis maiores são reduzidos ao novo máximo.

# 0.2.2 — 22/11/2026

- Corrigida a curva Reforçada: a equivalência de 2× continua até o topo (40% → 80%, 100% → 200%, 150% → 300%), antes da proteção final.
- Removida a redução progressiva do reforço acima de 40%; ganho continua aumentando entre 80% e 100%.
- Atualização permitida com a saída salva temporariamente desconectada, mantendo o destino.
- Atualizações preservam o nível de escuta anterior por conversão única da porcentagem.
- Troca para a curva Padrão respeita seu alcance máximo; interface e documentação explicam a diferença.

# 0.2.1 — 22/11/2026

- Controle liberado até 150% no aplicativo e no KDE, sem retorno automático a 100%.
- Curva 0–100% preservada; faixa adicional passa pela proteção final de picos.
- Volumes ampliados preservados na reinicialização e na troca de curva.

# 0.2.0 — 22/11/2026

- Saída padrão integrada ao KDE, curva 40% ≈ antigos 80%, 0% mudo e máximo preservado.
- Controle de volume depois da dinâmica e proteção final.
- Instalação gráfica, janela, bandeja, seleção de saída e restauração/desinstalação.
- Migração sem duplicar o filtro antigo; reconhecimento do plugin legado após desinstalação.
- Espera/reconexão de dispositivo, limitação de volume acima de 100%, transições silenciadas e recuperação de falha.
