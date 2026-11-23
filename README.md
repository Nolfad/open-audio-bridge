# Open Audio Bridge 0.3.0

Controle de volume integrado ao KDE, com instalação gráfica e restauração do áudio anterior. Validado em Tuxedo OS, com PipeWire 1.6.8 e WirePlumber 0.5.15.

[![Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml/badge.svg)](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml)

## Baixar e instalar

Baixe o ZIP do instalador na [última release](https://github.com/Nolfad/open-audio-bridge/releases/latest). Em **Assets**, escolha **open-audio-bridge-0.3.0.zip**, extraia e siga os passos abaixo. O download é público, sem necessidade de entrar no GitHub. O arquivo `SHA256SUMS` permite conferir a integridade do pacote.

Para testar alterações ainda não lançadas, há pacotes temporários em [Actions → Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml), na seção **Artifacts** de cada execução aprovada. Esses arquivos exigem login e ficam disponíveis por 30 dias.

## Instalar

1. Extraia o ZIP em uma pasta.
2. Abra **Instalar.desktop** (aparece como **Instalar Open Audio Bridge**).
3. Clique em **Instalar e ativar**. Se o KDE pedir, autorize a execução do lançador.
4. Clique em **Abrir controle**. Depois, abra **Open Audio Bridge** pelo menu de aplicativos.

A instalação fica na sua conta, sem sudo. A pasta extraída pode ser removida depois. Atualizações usam o mesmo instalador e preservam a configuração anterior. Na migração da saída virtual, o nível anterior é convertido para a nova escala. A primeira ativação limita o fone anteriormente escolhido a 50% e as demais saídas a 35%; depois você pode ajustar normalmente até 150%. Atualizações do modo nativo preservam os volumes dos dispositivos.

Dependências: Python 3, PyQt5, gcc, PipeWire 1.6+, WirePlumber 0.5.15+, pipewire-pulse, pw-cli, pw-dump e pactl (pacote pulseaudio-utils) e systemd de usuário. Se faltar algum componente, o instalador informa antes de alterar o áudio. O pacote inclui o código-fonte; o instalador compila os dois plugins para o computador de destino. Não é um executável independente de dependências.

## Usar

- Em **Ouvir em**, deixe **Padrão do sistema**. Escolha o fone ou monitor diretamente no KDE: o processamento acompanha a saída escolhida.
- Para restringir o efeito, escolha uma saída fixa em **Ouvir em**. Isso limita o processamento a ela, sem mudar a saída padrão nem mover aplicativos.
- Não há saída virtual Open Audio Bridge: o controle da janela e o do KDE ajustam o mesmo dispositivo.
- Use o controle do KDE, as teclas de volume ou o controle da janela. A janela permite chegar a 150%; no KDE, ative a opção de permitir volume acima de 100% se ela estiver desmarcada.
- **Reforçada:** acrescenta 20 pontos percentuais à escala original: 40% ≈ antigos 60%, 80% ≈ antigos 100%, 100% ≈ antigos 120% e 150% ≈ antigos 170%, antes da proteção de picos. Entre 0% e 20%, o reforço entra gradualmente para manter silêncio em zero e controle dos níveis baixos.
- **Padrão:** mantém a escala anterior. Trocar a curva preserva o nível atual quando ele cabe na escala escolhida, ajustando a porcentagem mostrada. Ao sair de Reforçada acima de 130%, a escala Padrão chega ao limite de 150% e o nível é reduzido.
- **Silenciar** e 0% produzem silêncio.
- **Desativar** remove o efeito e restaura o controle original do dispositivo, preservando a porcentagem e o estado mudo atuais. O nível percebido pode mudar ao remover a equalização e o reforço.
- Fechar a janela deixa o processamento ativo, sem um segundo ícone na bandeja. Abra pelo menu de aplicativos quando precisar. A bandeja é opcional usando `gui.py --tray`.

O efeito é inserido dentro das saídas reais estéreo. No modo automático, as saídas disponíveis ficam preparadas para que a troca no KDE não dependa de abrir a janela. As regras do próprio sistema decidem a saída após uma desconexão. No modo fixo, o efeito aguarda aquela saída; outras continuam com áudio original.

A integração local foi validada com saídas ALSA USB (HyperX Cloud Flight) e HDMI. Saídas surround e controles de volume por hardware de Bluetooth não são suportados nesta versão. Os microfones não recebem processamento nem alterações de ganho.

## Desinstalar

Clique em **Desinstalar** na janela. O programa restaura os arquivos, a saída padrão e os volumes/mudo preservados na instalação. Os volumes são restaurados nas saídas conectadas. Arquivos anteriores e cópias de segurança das atualizações ficam registrados em `~/.local/state/open-audio-bridge-desktop` e `~/.local/state/open-audio-bridge-upgrades`.

Não use os comandos de instalação da versão 0.1 enquanto a versão gráfica está ativa: eles poderiam duplicar o processamento. O comando antigo foi protegido para informar esse conflito.

## O que mudou no volume

A nova versão não aumenta novamente o ganho antes do limitador. Ela preserva a equalização e a dinâmica do perfil anterior `loudness-safe` (+18 dB, teto de amostra −4 dBFS) e muda a curva do controle depois desse processamento. Uma proteção final vem depois do controle.

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

A proteção final continua com teto de amostra −4 dBFS. Se o sinal amplificado atingir esse teto, o limitador reduz os picos e pode alterar a dinâmica; a tabela descreve o ganho solicitado antes dessa proteção, não uma garantia de volume acústico ilimitado. Não há promessa de reproduzir drivers do Windows ou eliminar distorção prévia. O controle permanece limitado a 150%.

## Validação

Testes automatizados cobrem: curva, preservação de forma de onda, silêncio, balanço, limites, configuração, restauração de arquivos, falhas de atualização, transição com saída silenciada e interação gráfica.

Os testes automatizados verificam a progressão em toda a faixa, inclusive entre 80% e 100%, o equivalente a 120% em 100%, a migração sem salto de nível e a troca de curvas com limite. A referência é o perfil 0.1 `loudness-safe` seguido da atenuação cúbica do PipeWire; não é uma medição acústica ou comparação física com o Windows.

Na validação local com o processamento nativo em saída de teste isolada das saídas físicas, sinais baixos confirmaram 80% equivalente ao antigo 100% e +4,75 dB ao subir de 80% para 100%. Em sinal forte a 150%, o pico ficou no teto de −4 dBFS; 0% produziu silêncio. O limitador é de amostras com margem de −4 dBFS, não um true-peak certificado para todo conteúdo.

A integração real foi verificada alternando HyperX e HDMI como padrão, selecionando destino fixo, controlando o volume por ambos os caminhos e desativando/reativando o efeito. O ganho do microfone permaneceu inalterado. O perfil de hardware só modifica os controles de reprodução, com cópia privada reversível; o perfil de captura permanece original.

## Desenvolvimento

`python3 -m unittest discover -s tests -v` executa os testes. A interface usa PyQt5; o áudio funciona em serviço de usuário separado. O código e a licença MIT acompanham o pacote.

### Gerar o pacote localmente

Em Tuxedo OS/Ubuntu, os componentes de build são `gcc`, `python3` e `python3-pyqt5`. Depois execute:

```sh
python3 tools/build.py
cd dist
sha256sum -c SHA256SUMS
```

O script compila os dois plugins com avisos tratados como erros e executa os testes em uma cópia temporária. Só gera `dist/open-audio-bridge-0.3.0.zip` e `dist/SHA256SUMS` se tudo passar. O pacote preserva a permissão de execução do lançador e não inclui configurações pessoais, bibliotecas compiladas ou caches. A mesma fonte gera o mesmo ZIP.

O GitHub Actions executa esse processo em Ubuntu 24.04 a cada push, pull request ou execução manual. Os testes não precisam de placa de som e não alteram o áudio da máquina. A validação do CI cobre o processamento e as simulações de configuração/interface; integração com o servidor de áudio e dispositivos reais continua sendo uma verificação local.

### Publicar uma versão

Atualize `VERSION` em `bridge.py`, o `CHANGELOG.md` e os exemplos do README. Envie o commit e uma tag no formato `vX.Y.Z` correspondente à versão. O workflow confere a tag, compila e testa o pacote e, somente após o sucesso, cria uma release pública com o instalador e `SHA256SUMS`. Pushes comuns continuam gerando apenas builds de desenvolvimento.

O workflow prepara a release como rascunho antes de publicá-la. Se uma publicação falhar e deixar um rascunho, confira o erro e remova somente esse rascunho antes de executar novamente; releases existentes não são sobrescritas automaticamente.
