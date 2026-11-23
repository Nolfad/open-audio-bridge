"""Independent loudness drive and post-volume tone controls."""
import math

FREQUENCIES=(31.5,63,125,250,500,1000,2000,4000,8000,16000)
LABELS=('31','63','125','250','500','1k','2k','4k','8k','16k')
# Original, moderate starting points; not licensed or copied vendor curves.
PRESETS={
 'flat':('Neutro',(0,0,0,0,0,0,0,0,0,0)),
 'music':('Música',(1,2,1,0,-1,0,1,1,1,0)),
 'rock':('Rock',(2,3,2,0,-1,-1,1,2,2,1)),
 'pop':('Pop',(1,2,1,0,1,2,2,1,1,0)),
 'funk':('Funk',(3,4,3,0,-1,0,1,1,2,1)),
 'movie':('Filme',(2,3,2,0,-1,1,2,2,0,0)),
 'voice':('Voz',(-3,-3,-2,-1,0,2,3,2,0,-1)),
}

def normalize(value=None):
 if value is None:value={}
 if not isinstance(value,dict):raise ValueError('Configuração de som inválida.')
 drive=value.get('drive_db',18.)
 if isinstance(drive,bool) or not isinstance(drive,(int,float)) or not math.isfinite(drive) or not 0<=drive<=18:raise ValueError('Reforço deve estar entre 0 e 18 dB.')
 enabled=value.get('eq_enabled',False)
 if type(enabled) is not bool:raise ValueError('Estado do equalizador inválido.')
 preset=value.get('preset','flat')
 if not isinstance(preset,str) or preset not in (*PRESETS,'custom'):raise ValueError('Preset desconhecido.')
 bands=value.get('bands',[0.]*10)
 if not isinstance(bands,(list,tuple)) or len(bands)!=10 or any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not -6<=x<=6 for x in bands):raise ValueError('Use dez bandas entre −6 e +6 dB.')
 if preset!='custom':bands=PRESETS[preset][1]
 return {'drive_db':float(drive),'eq_enabled':enabled,'preset':preset,'bands':[float(x) for x in bands]}

def filters(value=None):
 config=normalize(value)
 if not config['eq_enabled']:return []
 return [{'type':'bq_peaking','freq':frequency,'gain':gain,'q':1.4} for frequency,gain in zip(FREQUENCIES,config['bands']) if gain!=0]
