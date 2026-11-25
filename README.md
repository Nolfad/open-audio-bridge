# Open Audio Bridge 0.6.0

Controle de volume integrado ao KDE, com instalação gráfica e restauração do áudio anterior. Validado em Tuxedo OS, com PipeWire 1.6.8 e WirePlumber 0.5.15.

[![Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml/badge.svg)](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml)

## Baixar e instalar

**Tuxedo OS, Ubuntu ou Debian compatível: [baixar instalador .deb — arquivo único](https://github.com/Nolfad/open-audio-bridge/releases/download/v0.6.0/open-audio-bridge-installer_0.6.0_all.deb).**

Baixe somente o `.deb`: ele já contém o programa. Dê dois cliques no arquivo para abrir o gerenciador de programas e instalar. Depois abra **Instalar ou atualizar Open Audio Bridge** no menu e clique em **Instalar e ativar**. Não precisa baixar nem extrair o ZIP. O sistema pode baixar dependências e pedir a senha administrativa durante a instalação do pacote.

**Arch Linux: [baixar pacote .pkg.tar.zst](https://github.com/Nolfad/open-audio-bridge/releases/download/v0.6.0/open-audio-bridge-installer-0.6.0-1-any.pkg.tar.zst).** Veja as instruções abaixo.

A [última release](https://github.com/Nolfad/open-audio-bridge/releases/latest) também oferece o ZIP como alternativa. Os downloads são públicos, sem login no GitHub. O arquivo `SHA256SUMS` permite conferir a integridade dos pacotes.

Para testar alterações ainda não lançadas, há pacotes temporários em [Actions → Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml), na seção **Artifacts** de cada execução aprovada. Esses arquivos exigem login e ficam disponíveis por 30 dias.

## Instalar com .deb

1. Baixe **open-audio-bridge-installer_0.6.0_all.deb** e abra no gerenciador de programas. Ele instala as dependências; essa etapa usa a autorização administrativa normal do sistema.
2. Abra **Instalar ou atualizar Open Audio Bridge** no menu e clique em **Instalar e ativar**.
3. Depois use **Open Audio Bridge** no menu ou o ícone da bandeja.

O pacote é um **instalador**, sem scripts que alterem o áudio ao instalar pelo APT. A aplicação e suas atualizações ficam na conta do usuário. A versão mostrada pelo gerenciador de pacotes é a do instalador; a versão do programa aparece na aba Atualizações. Este download não configura um repositório APT. Para remover tudo, desinstale primeiro pelo aplicativo e depois remova o pacote `open-audio-bridge-installer`. Remover apenas o pacote não apaga aplicativos pessoais ou backups.

São necessários **PipeWire 1.6+ e WirePlumber 0.5.15+**. O .deb declara essas dependências e não tenta substituir o áudio de uma distribuição antiga ou adicionar repositórios externos.

## Instalar no Arch Linux

1. Baixe **open-audio-bridge-installer-0.6.0-1-any.pkg.tar.zst** da release.
2. Na pasta onde baixou o arquivo, execute:

   ```sh
   sudo pacman -U ./open-audio-bridge-installer-0.6.0-1-any.pkg.tar.zst
   ```

3. Abra **Instalar ou atualizar Open Audio Bridge** no menu e clique em **Instalar e ativar**.
4. Use **Open Audio Bridge** pelo menu ou pela bandeja normalmente.

O pacman resolve as dependências dos repositórios configurados. Mantenha o Arch atualizado, sem atualizações parciais. São necessários PipeWire 1.6+, WirePlumber 0.5.15+, `pipewire-audio`, `pipewire-pulse`, `libpulse` (fornece `pactl`), Python 3.10+, `python-pyqt5`, `qt5-wayland`, `gcc`, `glibc` e `systemd`. O programa depende de uma sessão com PipeWire/WirePlumber: quem ainda usa o servidor PulseAudio precisa migrar o áudio antes. Não confirme remoções de componentes sem revisar a transação do pacman.

O `.pkg.tar.zst` é um único arquivo instalável, sem extrair ZIP. Abrir com dois cliques depende de ter um gerenciador gráfico de pacotes associado; o comando acima funciona com o pacman padrão. O pacote instala apenas fontes e o iniciador, sem alterar o áudio das contas. Como no `.deb`, o aplicativo e suas atualizações ficam na sua conta. Uma instalação anterior gerenciada pode ser atualizada pelo instalador, sem desinstalar antes. Para remover tudo, use primeiro **Configurações → Desinstalar** no aplicativo e depois `sudo pacman -R open-audio-bridge-installer`.

Para compilar o pacote em vez de baixar o pronto, instale `base-devel`, baixe o arquivo **PKGBUILD** da mesma release para uma pasta vazia, confira seu conteúdo e execute `makepkg -si` como usuário normal. Ele baixa o ZIP oficial, confere o SHA256, compila e testa antes de empacotar. Este pacote não foi publicado no AUR nem configura um repositório pacman.

A construção, os testes e a instalação do pacote são verificados em um ambiente Arch no CI, incluindo a abertura da janela gráfica sem ativar o áudio. **Reprodução em hardware real no Arch ainda não foi validada.** Referências: [PKGBUILD/makepkg](https://man.archlinux.org/man/PKGBUILD.5.en), [pipewire-audio](https://archlinux.org/packages/extra/x86_64/pipewire-audio/), [WirePlumber](https://archlinux.org/packages/extra/x86_64/wireplumber/) e [libpulse/pactl](https://archlinux.org/packages/extra/x86_64/libpulse/files/).

## Instalar com ZIP

1. Extraia o ZIP em uma pasta.
2. Abra **Instalar.desktop** (aparece como **Instalar Open Audio Bridge**).
3. Clique em **Instalar e ativar**. Se o KDE pedir, autorize a execução do lançador.
4. Clique em **Abrir controle**. Depois, abra **Open Audio Bridge** pelo menu de aplicativos ou pelo ícone na bandeja.

A instalação fica na sua conta, sem sudo. A pasta extraída pode ser removida depois. Atualizações usam o mesmo instalador e preservam a configuração anterior. Na migração da saída virtual, o nível anterior é convertido para a nova escala. A primeira ativação limita o fone anteriormente escolhido a 50% e as demais saídas a 35%; depois você pode ajustar normalmente até 150%. Atualizações do modo nativo preservam os volumes dos dispositivos.

Dependências: Python 3, PyQt5, gcc e cabeçalhos de desenvolvimento da libc, PipeWire 1.6+, WirePlumber 0.5.15+, pipewire-pulse, pw-cli, pw-dump e pactl (pulseaudio-utils no Debian/Ubuntu ou libpulse no Arch) e systemd de usuário. Se faltar algum componente, o instalador informa antes de alterar o áudio. O pacote inclui o código-fonte; o instalador compila os plugins para o computador de destino. Não é um executável independente de dependências.

## Atualizações automáticas

A partir da versão 0.5, as atualizações automáticas ficam ativadas. O programa consulta a **última release estável** de `Nolfad/open-audio-bridge` a cada seis horas; um serviço da sua conta verifica pendências a cada quinze minutos. Não é necessário deixar a janela aberta. Computador desligado ou sessão encerrada não executam atualizações.

Quando há uma versão nova, a instalação automática aguarda não haver reprodução ativa. Se algum aplicativo mantém um fluxo aberto, ela pode continuar esperando. A aba **Atualizações** permite desligar a automação, ver o resultado da última busca ou usar **Buscar e atualizar agora**, que pode interromper o áudio por alguns instantes. Versões de desenvolvimento, prereleases e commits sem release não são instalados. Quem usa 0.4 ou anterior precisa instalar 0.5 uma vez para receber essa função.

Os pacotes vêm de URLs HTTPS fixas do repositório, têm tamanho limitado e passam pela conferência SHA256 e validação de caminhos/versão antes de executar o instalador. O checksum confere integridade; não é uma assinatura independente do GitHub. O instalador mantém cópias de segurança e restauração em caso de falha. Presets, ganho, volume, preferência de atualização e estado ativado/desativado são preservados. A interface 0.5 ou posterior recarrega sozinha ao concluir uma atualização, mantendo o ícone na bandeja.

As atualizações da aplicação não usam sudo. As dependências do sistema continuam sob responsabilidade do gerenciador de pacotes. Se uma versão futura exigir dependências indisponíveis, a atualização deve falhar sem substituir a instalação funcional; consulte a mensagem na aba Atualizações.

## Flatpak e Flathub

Esta versão não é um Flatpak nem foi enviada ao Flathub. O processamento atual carrega bibliotecas no PipeWire do host e configura serviços de usuário e perfis do WirePlumber. Empacotá-lo adequadamente em Flatpak requer separar ou adaptar essa integração, além de atender à revisão e às permissões do Flathub. Não usamos um Flatpak apenas para executar comandos fora do isolamento. Referências: [permissões Flatpak](https://docs.flatpak.org/en/latest/sandbox-permissions.html) e [requisitos Flathub](https://docs.flathub.org/docs/for-app-authors/requirements).

## Usar

- Em **Ouvir em**, deixe **Padrão do sistema**. Escolha o fone ou monitor diretamente no KDE: o processamento acompanha a saída escolhida.
- Para restringir o efeito, escolha uma saída fixa em **Ouvir em**. Isso limita o processamento a ela, sem mudar a saída padrão nem mover aplicativos.
- Não há saída virtual Open Audio Bridge: o controle da janela e o do KDE ajustam o mesmo dispositivo.
- Use o controle do KDE, as teclas de volume ou o controle da janela. A janela permite chegar a 150%; no KDE, ative a opção de permitir volume acima de 100% se ela estiver desmarcada.
- **Reforçada:** acrescenta 20 pontos percentuais à escala original: 40% ≈ antigos 60%, 80% ≈ antigos 100%, 100% ≈ antigos 120% e 150% ≈ antigos 170%, antes da proteção de picos. Entre 0% e 20%, o reforço entra gradualmente para manter silêncio em zero e controle dos níveis baixos.
- **Padrão:** mantém a escala anterior. Trocar a curva preserva o nível atual quando ele cabe na escala escolhida, ajustando a porcentagem mostrada. Ao sair de Reforçada acima de 130%, a escala Padrão chega ao limite de 150% e o nível é reduzido.
- **Silenciar** e 0% produzem silêncio.
- **Desativar** remove o efeito e restaura o controle original do dispositivo, preservando a porcentagem e o estado mudo atuais. O nível percebido pode mudar ao remover a equalização e o reforço.
- O ícone do Open Audio Bridge permanece na bandeja e inicia com a sessão. Clique nele para abrir a janela, ativar/desativar o efeito ou conferir o estado. Fechar a janela mantém o ícone e o processamento ativos. O ícone de áudio do KDE continua controlando o mesmo volume.

O efeito é inserido dentro das saídas reais estéreo. No modo automático, as saídas disponíveis ficam preparadas para que a troca no KDE não dependa de abrir a janela. As regras do próprio sistema decidem a saída após uma desconexão. No modo fixo, o efeito aguarda aquela saída; outras continuam com áudio original.

A integração local foi validada com saídas ALSA USB (HyperX Cloud Flight) e HDMI. Saídas surround e controles de volume por hardware de Bluetooth não são suportados nesta versão. Os microfones não recebem processamento nem alterações de ganho.

## Configurações e inicialização

A aba **Configurações** reúne **Iniciar com o sistema** e **Desinstalar**.

**Iniciar com o sistema** controla a abertura do ícone da bandeja e a inicialização do processamento ao entrar na sua conta. O processamento só inicia se estiver ativado. Desmarcar essa opção não interrompe o áudio atual: a mudança vale para a próxima sessão. Para parar o efeito agora, use **Desativar**.

Você pode abrir o programa pelo menu quando quiser, mesmo com a inicialização automática desligada. A abertura manual retoma o processamento que estava ativado, sem ligar novamente a inicialização automática. Atualizações preservam essa preferência e não iniciam um processamento que estava parado. A busca de atualizações tem sua própria opção na aba **Atualizações**.

## Ganho e equalizador independentes

A aba **Volume e ganho** reúne a curva de volume e o **Reforço máximo adaptativo** (0–18 dB). Esse valor não é um ganho fixo: fontes baixas recebem reforço quando existe margem, enquanto gravações já fortes recebem menos. Não há compressor antes do controle de volume nem duas etapas de limitação.

Na aba **Experiência musical**, escolha **Música — Quente**, **Eletrônica — Graves e clareza** ou **Sem processamento musical**. Os dois modos analisam lentamente a distribuição de energia da gravação e adicionam reforços moderados de graves e detalhes; não cortam o grave original para obter volume. A **Amplitude estéreo** (0–25%) expande suavemente apenas a componente lateral acima dos graves, preservando o centro e sinais mono. São efeitos próprios para reprodução estéreo, não um decodificador ou renderizador Dolby Atmos.

Na aba **Equalizador**, selecione um preset (Neutro, Música, Rock, Pop, Funk, Filme, Voz) ou ajuste individualmente as dez bandas de −6 a +6 dB. A equalização manual e o modo musical são independentes e são preservados nas atualizações.

Cadeia: **modo musical opcional → EQ manual opcional → ganho adaptativo, volume e proteção antecipada de picos em um único estágio**. O estágio final utiliza estimativa de true peak com interpolação 4×, margem adicional e atraso de aproximadamente 6–7 ms a 48 kHz; a recuperação lenta do ganho evita nivelar o áudio a cada batida. O teto nominal é −1,2 dBTP; nenhum limitador garante ausência de distorção no alto-falante ou amplificador físico. O resultado de uma gravação já no máximo digital não pode crescer indefinidamente sem reduzir dinâmica ou usar ganho físico.

Ao atualizar, a curva manual, o destino, a preferência de início e o reforço são preservados. Os novos modos começam desligados para permitir comparação direta. Se a interface antiga estiver aberta, ela se recarrega quando não há alterações pendentes.

## Desinstalar

Na aba **Configurações**, clique em **Desinstalar**. O programa restaura os arquivos, a saída padrão e os volumes/mudo preservados na instalação. Os volumes são restaurados nas saídas conectadas. Arquivos anteriores e cópias de segurança das atualizações ficam registrados em `~/.local/state/open-audio-bridge-desktop` e `~/.local/state/open-audio-bridge-upgrades`.

Não use os comandos de instalação da versão 0.1 enquanto a versão gráfica está ativa: eles poderiam duplicar o processamento. O comando antigo foi protegido para informar esse conflito.

## O que mudou no volume

A curva de volume continua igual. O novo processador usa o ganho solicitado como máximo, aplica um orçamento de picos progressivo para manter controle útil em gravações fortes e evita limitar o áudio duas vezes.

| Controle novo | Escala antiga equivalente |
|---:|---:|
| 0% | 0% |
| 10% | 20% |
| 20% | 40% |
| 30% | 50% |
| 40% | 60% |
| 60% | 80% |
| 80% | 100% |
| 100% | 120% |
| 125% | 145% |
| 150% | 170% |

A partir de 20%, a relação é `escala original equivalente = controle + 20`. Abaixo disso, `equivalente = 2 × controle`, ligando o silêncio à curva de forma contínua. São **20 pontos percentuais**, não 20% de ganho nem o dobro do volume. Como o PipeWire usa volume cúbico, a amplitude nessa etapa é `(equivalente / 100)³`. Em sinal com margem, subir de 80% para 100% acrescenta aproximadamente 4,75 dB.

A tabela descreve o ganho máximo solicitado, antes da adaptação de picos. Em uma gravação forte, o volume se aproxima do limite digital ao chegar a 100%; acima disso, ganho adicional só é possível em conteúdo que ainda tenha margem. O controle permanece limitado a 150%.

## Validação

Testes automatizados cobrem: curva, preservação de forma de onda, silêncio, balanço, limites, configuração, restauração de arquivos, falhas de atualização, transição com saída silenciada e interação gráfica.

Os testes automatizados verificam a progressão em toda a faixa, inclusive entre 80% e 100%, o equivalente a 120% em 100%, a migração sem salto de nível e a troca de curvas com limite. A referência é o perfil 0.1 `loudness-safe` seguido da atenuação cúbica do PipeWire; não é uma medição acústica ou comparação física com o Windows.

Os testes do novo plugin usam sinais multitonais com graves fortes, agudos simultâneos, picos entre amostras, balanço estéreo, silêncio imediato, mudanças de volume, tamanhos de bloco variáveis e diferentes taxas de amostragem. A inspeção do sinal digital não substitui a comparação auditiva ou medição acústica da caixa de som.

A integração nativa preserva os controles de volume, roteamento e saída padrão do sistema; a configuração de captura não é alterada. Os modos musicais incluem testes de bypass exato, limites de reforço por banda, estabilidade e preservação de mono/centro.

## Desenvolvimento

`python3 -m unittest discover -s tests -v` executa os testes. A interface usa PyQt5; o áudio funciona em serviço de usuário separado. O código e a licença MIT acompanham o pacote.

### Gerar o pacote localmente

Em Tuxedo OS/Ubuntu, os componentes de build são `gcc`, `python3` e `python3-pyqt5`. Depois execute:

```sh
python3 tools/build.py
cd dist
sha256sum -c SHA256SUMS
```

O script compila os plugins com avisos tratados como erros e executa os testes em uma cópia temporária. Só gera `dist/open-audio-bridge-0.6.0.zip`, `dist/open-audio-bridge-installer_0.6.0_all.deb` e `dist/SHA256SUMS` se tudo passar. O build requer também `dpkg-deb` (pacote `dpkg`). O pacote preserva a permissão de execução do lançador e não inclui configurações pessoais, bibliotecas compiladas ou caches. A mesma fonte gera o mesmo ZIP. Também gera `dist/arch/PKGBUILD` com o SHA256 desse ZIP; em um Arch com `base-devel`, copie o ZIP para essa pasta e execute `makepkg -si` sem root para construir e instalar o pacote nativo.

O GitHub Actions executa esse processo em Ubuntu 24.04 a cada push, pull request ou execução manual. Uma segunda etapa usa o ambiente oficial `archlinux:base-devel`, executa os testes novamente e instala o pacote com pacman para verificar o iniciador gráfico. Os testes não precisam de placa de som e não alteram o áudio da máquina. A validação do CI cobre o processamento e as simulações de configuração/interface; integração com o servidor de áudio e dispositivos reais continua sendo uma verificação local.

### Publicar uma versão

Atualize `VERSION` em `bridge.py`, o `CHANGELOG.md` e os exemplos do README. Envie o commit e uma tag no formato `vX.Y.Z` correspondente à versão. O workflow confere a tag, compila e testa o pacote e, somente após o sucesso, cria uma release pública com os instaladores ZIP/.deb/.pkg.tar.zst, o `PKGBUILD` e um `SHA256SUMS` unificado. Pushes comuns continuam gerando apenas builds de desenvolvimento.

O workflow prepara a release como rascunho antes de publicá-la. Se uma publicação falhar e deixar um rascunho, confira o erro e remova somente esse rascunho antes de executar novamente; releases existentes não são sobrescritas automaticamente.
