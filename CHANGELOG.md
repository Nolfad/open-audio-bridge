# 1.0.0 — 25/11/2026

**Primeira versão estável do Open Audio Bridge.**

A versão 1.0.0 consolida a experiência validada pelo mantenedor e pelos primeiros usuários. É a mesma implementação aprovada na 0.7.2, sem mudanças no processamento sonoro ou na interface.

- Integração nativa com as saídas e o volume do sistema, acompanhando automaticamente a saída padrão ou permitindo selecionar uma saída fixa.
- Ganho adaptativo com proteção de picos, modos musicais, amplitude estéreo e equalizador independente de dez bandas com presets.
- Interface responsiva, transições suaves entre presets, medidores de energia por banda em tempo real e ícone de bandeja com início opcional.
- Instaladores de arquivo único para Debian/Ubuntu/Tuxedo OS compatíveis e Arch Linux, com atualizações automáticas e preservação das instalações gerenciadas.
- Requisitos mantidos: PipeWire 1.6+ e WirePlumber 0.5.15+. Validação em Tuxedo OS/KDE; empacotamento e abertura do instalador também testados no Arch pelo CI.

As próximas versões serão dedicadas a melhorias e correções de acordo com o uso real e a compatibilidade dos sistemas.

# 0.7.2 — 25/11/2026

- Interface do equalizador permanece responsiva ao ativar, desativar, trocar presets e ajustar as bandas, mesmo durante a aplicação do processamento. Alterações sucessivas são reunidas na configuração mais recente, sem que respostas atrasadas sobrescrevam os ajustes.
- Transição visual suave de 480 ms dos dez cursores ao selecionar um preset, validada no tema Breeze do KDE e no Fusion. A animação não aplica ganhos intermediários ao DSP.
- Medidores de energia real nas dez bandas da saída selecionada (−80 a 0 dBFS), independentes dos cursores de ganho. O monitor opera somente em memória, não captura o microfone e é suspenso quando a aba não está visível ou não há reprodução.
- Cabeçalho com duas linhas permanentes: o estado pode mudar para “Aplicando…” sem ocultar a saída selecionada ou deslocar as abas e os controles.
- Motor de áudio, curva de volume, presets, proteção de picos, seleção de saída e configurações da 0.6.1 preservados. Atualizações de instalações gerenciadas não exigem desinstalar a versão anterior.

# 0.6.1 — 25/11/2026

- Atualizações nativas preservam os perfis de áudio já preparados e suspendem apenas o processamento do Open Audio Bridge, evitando recriar as saídas e reiniciar desnecessariamente o WirePlumber.
- Atualizações automáticas aguardam pausa tanto na reprodução quanto na captura, incluindo chamadas e fluxos ativos silenciados. Quando não é possível confirmar o estado, a instalação é adiada.
- Quando uma mudança de perfil exigir reinício do gerenciador de áudio, são preservadas as rotas dos fluxos que continuam conectados e as saídas/entradas padrão.
- Testes de atualização e restauração sem reinício do servidor de áudio. O motor de processamento musical da 0.6.0 permanece inalterado.

# 0.6.0 — 25/11/2026

- Substitui a compressão e a dupla limitação do fluxo nativo por um ganho estéreo adaptativo único, com antecipação de picos, interpolação 4× e recuperação lenta para preservar contrastes musicais.
- A curva de volume mantém sua progressão; o reforço de até 18 dB passa a representar o ganho máximo disponível de acordo com a margem do sinal.
- Novo painel de experiência musical, com modos de timbre adaptativo Quente e Eletrônica e amplitude estéreo ajustável, independentes do EQ manual.
- Mantém o volume e os dispositivos do KDE, preferências da instalação e curva do usuário; novos efeitos começam desligados na migração.
- Novos testes de espectro, dinâmica, transientes, picos interamostras, silêncio e integração. Reprodução e qualidade sonora validadas pelo usuário no Tuxedo OS/KDE.

# 0.5.2 — 24/11/2026

- Pacote nativo `.pkg.tar.zst` para Arch Linux, com dependências declaradas e o mesmo instalador gráfico usado no Debian/Tuxedo.
- Releases incluem o pacote pronto e a receita `PKGBUILD` com SHA256 das fontes. A aplicação mantém suas atualizações automáticas na conta do usuário.
- CI constrói e testa em Arch, instala com pacman e verifica a janela do instalador antes de publicar. O teste não valida reprodução em hardware real no Arch.
- Documentadas instalação, migração sem desinstalar uma versão gerenciada e remoção. Sem publicação no AUR nesta versão.

# 0.5.1 — 24/11/2026

- Nova aba Configurações, com o botão Desinstalar fora da área principal de controle do áudio.
- Opção Iniciar com o sistema controla o ícone e o processamento na próxima sessão, sem interromper o áudio atual.
- A preferência é preservada nas atualizações. Abrir pelo menu permite usar o programa manualmente sem reativar a inicialização automática.
- Atualizações preservam também o processamento parado, evitando iniciar o áudio de quem optou por não abrir o programa na sessão.

# 0.5.0 — 23/11/2026

- Atualização automática pelas releases estáveis oficiais do GitHub, com conferência de versão e SHA256, extração segura e bloqueio de instalações simultâneas.
- Busca a cada seis horas; instalações pendentes aguardam pausa na reprodução, com nova tentativa a cada quinze minutos. Atualização manual disponível na nova aba Atualizações.
- Preserva presets, volumes, ganho, preferência de atualização e estado ativado/desativado. Backups e restauração continuam disponíveis.
- Interface recarrega após atualizar, mantendo janela/bandeja. Correção na restauração para preservar as travas de operações concorrentes.
- Novo instalador .deb para Tuxedo/Ubuntu/Debian compatíveis, com dependências declaradas. A aplicação e seu atualizador funcionam na conta do usuário; o .deb é um instalador, não um repositório APT.
- Exige PipeWire 1.6+ e WirePlumber 0.5.15+. Quem usa 0.4 ou anterior precisa instalar esta versão uma vez para habilitar a atualização automática.

# 0.4.0 — 23/11/2026

- Ganho protegido separado do equalizador de timbre: reforço ajustável de 0 a 18 dB, mantendo a pré-equalização leve existente.
- Nova aba Equalizador com dez bandas, presets Neutro, Música, Rock, Pop, Funk, Filme e Voz, e ajuste Personalizado de −6 a +6 dB.
- Presets próprios; alterar o timbre não muda ganho nem volume do KDE. Bypass do equalizador preserva a curva escolhida.
- Equalizador depois do volume e antes da proteção final de −4 dBFS. Transições silenciadas e persistência dos ajustes nas atualizações.
- Atualização e restauração dos plugins substituem os arquivos de forma atômica, preservando bibliotecas que o servidor de áudio ainda tenha carregadas.
- Bandeja, saída padrão automática e controle único de volume mantidos. Equalizador inicialmente desligado para preservar o som anterior.

# 0.3.1 — 23/11/2026

- Restaurado o ícone do Open Audio Bridge na bandeja por padrão, incluindo início com a sessão.
- Fechar a janela mantém o ícone disponível para reabrir os controles.
- O volume e a saída continuam integrados ao KDE; o ícone não cria outro dispositivo de áudio.

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
