# Open Audio Bridge 0.2.2

Controle de volume integrado ao KDE, com instalação gráfica e restauração do áudio anterior. Validado em Tuxedo OS, com PipeWire 1.6.8 e WirePlumber 0.5.15.

[![Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml/badge.svg)](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml)

## Baixar um build

Abra [Actions → Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml), selecione uma execução concluída com sucesso e baixe o arquivo em **Artifacts** (é necessário entrar no GitHub). Extraia o download para encontrar o ZIP de instalação e `SHA256SUMS`. Os artefatos ficam disponíveis por 30 dias; uma nova execução pode ser iniciada pelo botão **Run workflow**.

## Instalar

1. Extraia o ZIP em uma pasta.
2. Abra **Instalar.desktop** (aparece como **Instalar Open Audio Bridge**).
3. Clique em **Instalar e ativar**. Se o KDE pedir, autorize a execução do lançador.
4. Clique em **Abrir controle**. Depois, abra **Open Audio Bridge** pelo menu de aplicativos ou pela bandeja.

A instalação fica na sua conta, sem sudo. A pasta extraída pode ser removida depois. Atualizações usam o mesmo instalador e preservam a configuração anterior. Ao atualizar de 0.2.0/0.2.1, o nível de escuta é preservado: acima de 40% na curva Reforçada, a porcentagem inicial diminui para evitar um salto repentino. Depois disso, subir o controle usa a nova curva contínua.

Dependências: Python 3, PyQt5, gcc, PipeWire, pipewire-pulse, pactl (pacote pulseaudio-utils) e systemd de usuário. Se faltar algum componente, o instalador informa antes de alterar o áudio. O pacote inclui o código-fonte; o instalador compila os dois plugins para o computador de destino. Não é um executável independente de dependências.

## Usar

- Deixe **Open Audio Bridge** como saída padrão no KDE.
- Em **Ouvir em**, escolha o monitor, fone ou outra saída física estéreo.
- Use o controle do KDE, as teclas de volume ou o controle da janela. A janela permite chegar a 150%; no KDE, ative a opção de permitir volume acima de 100% se ela estiver desmarcada.
- **Reforçada:** cada porcentagem corresponde ao dobro da escala original: 40% ≈ antigos 80%, 80% ≈ antigos 160%, 100% ≈ antigos 200% e 150% ≈ antigos 300%, antes da proteção de picos. O reforço continua por toda a faixa.
- **Padrão:** mantém a escala anterior. Trocar a curva preserva o nível atual quando ele cabe na escala escolhida, ajustando a porcentagem mostrada. Ao sair de Reforçada acima de 75%, a escala Padrão chega ao limite de 150% e o nível é reduzido.
- **Silenciar** e 0% produzem silêncio.
- **Desativar** devolve o áudio à configuração anterior. **Ativar** retorna ao Open Audio Bridge.
- Fechar a janela deixa o processamento ativo. Ela continua disponível na bandeja.

O dispositivo físico permanece listado. Selecioná-lo diretamente no KDE contorna o Open Audio Bridge. Se isso ocorrer, a janela informa que é preciso selecionar Open Audio Bridge como saída padrão.

Se a saída selecionada desconectar, o programa mantém a saída virtual e aguarda a reconexão; não transfere o som para outro alto-falante automaticamente.

## Desinstalar

Clique em **Desinstalar** na janela. O programa restaura os arquivos, a saída padrão e os volumes/mudo preservados na instalação. Se uma saída usada estiver desconectada, o áudio é desativado e o programa pede para reconectá-la antes de concluir a restauração do volume dela. O registro é preservado até essa conclusão.

Não use os comandos de instalação da versão 0.1 enquanto a versão gráfica está ativa: eles poderiam duplicar o processamento. O comando antigo foi protegido para informar esse conflito.

## O que mudou no volume

A nova versão não aumenta novamente o ganho antes do limitador. Ela preserva a equalização e a dinâmica do perfil anterior `loudness-safe` (+18 dB, teto de amostra −4 dBFS) e muda a curva do controle depois desse processamento. Uma proteção final vem depois do controle.

| Controle novo | Escala antiga equivalente |
|---:|---:|
| 0% | 0% |
| 10% | 20% |
| 20% | 40% |
| 30% | 60% |
| 40% | 80% |
| 50% | 100% |
| 60% | 120% |
| 80% | 160% |
| 100% | 200% |
| 125% | 250% |
| 150% | 300% |

A relação é `escala original equivalente = 2 × controle`, em toda a faixa. Como o PipeWire usa volume cúbico, isso significa ganho de amplitude `((2 × controle) / 100)³` nessa etapa. Em sinal com margem, subir de 80% para 100% acrescenta aproximadamente 5,81 dB; o reforço não desaparece no topo. Não significa que a sensação de volume dobre.

A proteção final continua com teto de amostra −4 dBFS. Se o sinal amplificado atingir esse teto, o limitador reduz os picos e pode alterar a dinâmica; a tabela descreve o ganho solicitado antes dessa proteção, não uma garantia de volume acústico ilimitado. Não há promessa de reproduzir drivers do Windows ou eliminar distorção prévia. O controle permanece limitado a 150%.

## Validação

38 testes automatizados: curva, preservação de forma de onda, silêncio, balanço, limites, configuração, restauração de arquivos, falhas de atualização, transição com saída silenciada e interação gráfica.

Os testes automatizados verificam a progressão em toda a faixa, inclusive entre 80% e 100%, o equivalente a 200% em 100%, a migração sem salto de nível e a troca de curvas com limite. A referência é o perfil 0.1 `loudness-safe` seguido da atenuação cúbica do PipeWire; não é uma medição acústica ou comparação física com o Windows.

Na validação local com grafo PipeWire isolado das saídas físicas, sinais baixos confirmaram +18,06 dB em 100% frente ao antigo 100% e +5,81 dB ao subir de 80% para 100%. Em sinal forte a 150%, o pico ficou no teto de −4 dBFS; 0% produziu silêncio. O limitador é de amostras com margem de −4 dBFS, não um true-peak certificado para todo conteúdo.

## Desenvolvimento

`python3 -m unittest discover -s tests -v` executa os testes. A interface usa PyQt5; o áudio funciona em serviço de usuário separado. O código e a licença MIT acompanham o pacote.

### Gerar o pacote localmente

Em Tuxedo OS/Ubuntu, os componentes de build são `gcc`, `python3` e `python3-pyqt5`. Depois execute:

```sh
python3 tools/build.py
cd dist
sha256sum -c SHA256SUMS
```

O script compila os dois plugins com avisos tratados como erros e executa os testes em uma cópia temporária. Só gera `dist/open-audio-bridge-0.2.2.zip` e `dist/SHA256SUMS` se tudo passar. O pacote preserva a permissão de execução do lançador e não inclui configurações pessoais, bibliotecas compiladas ou caches. A mesma fonte gera o mesmo ZIP.

O GitHub Actions executa esse processo em Ubuntu 24.04 a cada push, pull request ou execução manual. Os testes não precisam de placa de som e não alteram o áudio da máquina. A validação do CI cobre o processamento e as simulações de configuração/interface; integração com o servidor de áudio e dispositivos reais continua sendo uma verificação local.
