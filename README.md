# Open Audio Bridge 0.2.1

Controle de volume integrado ao KDE, com instalação gráfica e restauração do áudio anterior. Validado em Tuxedo OS, com PipeWire 1.6.8 e WirePlumber 0.5.15.

[![Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml/badge.svg)](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml)

## Baixar um build

Abra [Actions → Build Linux](https://github.com/Nolfad/open-audio-bridge/actions/workflows/build.yml), selecione uma execução concluída com sucesso e baixe o arquivo em **Artifacts** (é necessário entrar no GitHub). Extraia o download para encontrar o ZIP de instalação e `SHA256SUMS`. Os artefatos ficam disponíveis por 30 dias; uma nova execução pode ser iniciada pelo botão **Run workflow**.

## Instalar

1. Extraia o ZIP em uma pasta.
2. Abra **Instalar.desktop** (aparece como **Instalar Open Audio Bridge**).
3. Clique em **Instalar e ativar**. Se o KDE pedir, autorize a execução do lançador.
4. Clique em **Abrir controle**. Depois, abra **Open Audio Bridge** pelo menu de aplicativos ou pela bandeja.

A instalação fica na sua conta, sem sudo. A pasta extraída pode ser removida depois. Atualizações usam o mesmo instalador e preservam a configuração anterior.

Dependências: Python 3, PyQt5, gcc, PipeWire, pipewire-pulse, pactl (pacote pulseaudio-utils) e systemd de usuário. Se faltar algum componente, o instalador informa antes de alterar o áudio. O pacote inclui o código-fonte; o instalador compila os dois plugins para o computador de destino. Não é um executável independente de dependências.

## Usar

- Deixe **Open Audio Bridge** como saída padrão no KDE.
- Em **Ouvir em**, escolha o monitor, fone ou outra saída física estéreo.
- Use o controle do KDE, as teclas de volume ou o controle da janela. A janela permite chegar a 150%; no KDE, ative a opção de permitir volume acima de 100% se ela estiver desmarcada.
- **Reforçada:** 40% corresponde aproximadamente aos antigos 80%; 100% continua com o mesmo nível anterior; de 100% a 150% há amplificação adicional com proteção de picos.
- **Padrão:** mantém a escala anterior. Trocar a curva preserva o nível atual, ajustando a porcentagem mostrada.
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
| 60% | 86,7% |
| 80% | 93,3% |
| 100% | 100% |
| 125% | 125% (amplificação adicional) |
| 150% | 150% (amplificação adicional) |

Até 100%, a curva é uma multiplicação de volume e não acrescenta compressão à forma de onda em nível constante. Acima de 100%, o limitador final pode reduzir os picos: o reforço depende da margem do conteúdo e pode alterar a dinâmica. O volume máximo permitido no controle é 150%. A dinâmica que já existia no perfil foi mantida. Isso não é uma promessa de reproduzir drivers do Windows ou de eliminar toda distorção prévia.

## Validação

34 testes automatizados: curva, preservação de forma de onda, silêncio, balanço, limites, configuração, restauração de arquivos, falhas de atualização, transição com saída silenciada e interação gráfica.

No grafo digital executado no PipeWire, o novo 40% diferiu do modelo da saída antiga em 80% por cerca de 0,0004 dB RMS; 100% manteve o mesmo nível. Os testes também verificaram 0%, desconexão/reconexão, inicialização com saída ausente, limite de 150%, atualização, desinstalação e reinstalação reais.

A referência usa o perfil 0.1 `loudness-safe` e a atenuação cúbica posterior do PipeWire; não é uma medição acústica do monitor ou uma comparação física com o Windows. O limitador é de amostras, com margem de −4 dBFS, não um true-peak certificado para todo conteúdo.

## Desenvolvimento

`python3 -m unittest discover -s tests -v` executa os testes. A interface usa PyQt5; o áudio funciona em serviço de usuário separado. O código e a licença MIT acompanham o pacote.

### Gerar o pacote localmente

Em Tuxedo OS/Ubuntu, os componentes de build são `gcc`, `python3` e `python3-pyqt5`. Depois execute:

```sh
python3 tools/build.py
cd dist
sha256sum -c SHA256SUMS
```

O script compila os dois plugins com avisos tratados como erros e executa os testes em uma cópia temporária. Só gera `dist/open-audio-bridge-0.2.1.zip` e `dist/SHA256SUMS` se tudo passar. O pacote preserva a permissão de execução do lançador e não inclui configurações pessoais, bibliotecas compiladas ou caches. A mesma fonte gera o mesmo ZIP.

O GitHub Actions executa esse processo em Ubuntu 24.04 a cada push, pull request ou execução manual. Os testes não precisam de placa de som e não alteram o áudio da máquina. A validação do CI cobre o processamento e as simulações de configuração/interface; integração com o servidor de áudio e dispositivos reais continua sendo uma verificação local.
