# Chuva na F1: onde mais chove na hora da corrida?

Spa e Silverstone têm fama de chuva. Este projeto mede, com 30 anos de clima, a chance de chover durante cada corrida do calendário de 2026 da Fórmula 1, na data e no horário de cada GP.

**Resultado:** Áustria (40%) e Interlagos (39%) empatam no topo. As duas têm cerca do dobro da chance de Spa (19%) e de Silverstone (18%).

## Resultados

Chance de chover (0,5 mm ou mais) nas 2 horas seguintes à largada, na data e no horário UTC do GP de 2026, contando 3 dias antes e depois, de 1996 a 2025 (210 janelas por pista).

| Pista | Chance | Intervalo de 95% |
|---|---|---|
| Áustria | 40% | 32% a 48% |
| Interlagos | 39% | 31% a 47% |
| Malásia (Sepang) | 30% | 22% a 38% |
| Mônaco | 20% | 12% a 29% |
| Spa | 19% | 12% a 26% |
| Silverstone | 18% | 12% a 23% |
| Suzuka | 18% | 14% a 22% |

As outras 16 corridas ficam entre 0% e 16%. Abu Dhabi, Catar e Baku ficam perto de zero. A tabela completa sai em `resultados/ranking.csv`.

**Interlagos contra as outras**, comparando nos mesmos anos sorteados:

| Contra | Diferença | Intervalo de 95% | Razão |
|---|---|---|---|
| Áustria | -1 ponto | -12 a +10 | 0,98 (empate) |
| Spa | +20 pontos | +9 a +31 | 2,05 |
| Silverstone | +21 pontos | +12 a +31 | 2,16 |

**O critério muda o 1º lugar, mas não o grupo da frente:**
- com 0,2 mm, Interlagos fica em 1º (58% contra 51% da Áustria);
- com 0,5, 1 e 2 mm, a Áustria fica na frente.

Nos quatro critérios, Áustria, Interlagos e Malásia são as três primeiras.

**Interlagos mês a mês** (todos os dias, das 14h às 16h de Brasília, 1996 a 2025):

| jan | fev | mar | abr | mai | jun | jul | ago | set | out | nov | dez |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 69% | 67% | 63% | 32% | 17% | 11% | 9% | 11% | 19% | 32% | 43% | 54% |

## O dado enxerga a chuva de verdade? (validação)

O ERA5 foi comparado com as corridas reais de 2023 a 1º/11/2026 (89 corridas). Conta como corrida molhada aquela em que 10% ou mais das voltas foram com pneu intermediário ou de chuva (dados da OpenF1).

- **Corridas molhadas: 8. O ERA5 marcou chuva em 6.** Acertou Mônaco 2023, Montreal 2024, Silverstone 2024, Interlagos 2024, Melbourne 2025 e Spa 2025. Perdeu Zandvoort 2023 e Silverstone 2025.
- **Corridas secas: 81. Alarme falso em 6.** Foram Miami 2023, 2025 e 2026, Áustria 2023 e 2026, e Suzuka 2025.

Duas das quatro corridas recentes na Áustria tiveram alarme falso. A amostra é pequena demais para concluir algo, mas é um ponto a observar.

## Método

1. **Calendário:** corridas de 2026 da OpenF1, sem as canceladas (Bahrein e Jeddah).
2. **Clima:** reanálise ERA5 (ECMWF), chuva hora a hora, pela API de histórico da Open-Meteo. É uma reconstrução do clima com observações e modelo, numa grade de cerca de 25 km.
3. **Tudo em UTC:** a hora UTC da largada de 2026 é usada em todos os anos. A opção `timezone=auto` da Open-Meteo usa o fuso de hoje para o período inteiro e ignora o horário de verão. Isso deslocava em 1 hora a janela das pistas da Europa e da América do Norte, e foi corrigido.
4. **Chuva na corrida:** 0,5 mm ou mais nas 2 horas seguintes à largada. Se a largada não é em hora cheia, a primeira e a última hora entram proporcionalmente.
5. **Incerteza:** bootstrap sorteando anos inteiros (2.000 repetições, semente 2026). As comparações entre pistas usam os mesmos sorteios para as duas. Empates dividem o 1º lugar.
6. **Validação:** usa a largada real (início da volta 1), porque corridas atrasam. Spa 2025 largou 1h20 depois do previsto. Nessa corrida, os stints da OpenF1 marcam pneu intermediário só na volta 1. O valor foi corrigido à mão para 25% das voltas, com base no relato da corrida: largada de intermediário e troca para slick nas voltas 12 e 13, de 44.

## Limitações

- O ERA5 mede uma área de cerca de 25 km, não a pista. Ele suaviza chuvas curtas e localizadas e pode errar o horário em uma ou duas horas.
- Ele não acerta igual em todo clima. Em lugares de chuva forte e curta, como Malásia e Singapura, tende a espalhar a chuva em mais horas e com menos intensidade.
- A chance vale para a data e o horário de 2026. Várias corridas foram em outras datas no passado.
- Interlagos teve horário de verão até 2019. O script usa sempre 17h UTC, que hoje é 14h em Brasília.
- Mostra o clima esperado, não prevê uma corrida específica.

## Como rodar

```
python -m pip install -r requirements.txt
python -m playwright install chromium
python chuva_calendario.py
python gerar_carrossel.py
```

- **`chuva_calendario.py`:** baixa os dados (de 20 a 30 minutos na primeira vez), faz as contas e os gráficos técnicos. Tudo fica guardado em `dados/`.
  - Para refazer só as contas, sem internet: `python chuva_calendario.py --so-analise`.
  - Se aparecer "o limite de pedidos acabou", rode de novo mais tarde. O que já foi baixado não se perde.
- **`gerar_carrossel.py`:** monta as 4 páginas do carrossel do LinkedIn com os números de `resultados/`.
  - Confere se os títulos continuam verdadeiros e avisa no terminal se algum deixou de valer.
  - Usa o modelo de design B. Para testar outro, use `--modelo A` (de A a E).
- O comando `playwright install chromium` só precisa ser rodado uma vez. Ele baixa o navegador que transforma o HTML do carrossel em imagem.
- Não precisa de conta, chave nem assinatura.

## Arquivos

| Arquivo | O que é |
|---|---|
| `chuva_calendario.py` | Coleta, validação, ranking, intervalos e gráficos técnicos |
| `gerar_carrossel.py` | Carrossel do LinkedIn a partir dos resultados |
| `carrossel/carrossel.html` | Desenho do carrossel. Aberto no navegador, vira um editor visual com todas as opções de design |
| `resultados/resumo.txt` | Todas as contas, as mesmas impressas no terminal |
| `resultados/ranking.csv` | Chance por pista, intervalo, chance de ficar em 1º |
| `resultados/diferencas_interlagos.csv` | Interlagos contra as outras, com intervalo |
| `resultados/validacao.csv` | Corridas de 2023 em diante: largada programada e real, voltas com pneu de chuva, chuva do ERA5 |
| `resultados/janelas.csv` | Chuva em cada janela (pista, ano, dia) |
| `resultados/interlagos_dias.csv` | Interlagos, das 14h às 16h, todos os dias de 1996 a 2025 |
| `chuva_ranking.png`, `chuva_interlagos_ano.png` | Gráficos técnicos |
| `carrossel/saida/` | Páginas do carrossel (PNG) e o PDF |

## Fontes e licenças

- **Clima:** [Open-Meteo](https://open-meteo.com), API de histórico (dados sob licença CC BY 4.0), com a reanálise ERA5. Contém informação modificada do Copernicus Climate Change Service (2026). Nem a Comissão Europeia nem o ECMWF respondem pelo uso desses dados.
- **Calendário, largadas e pneus:** [OpenF1](https://openf1.org), API aberta e não oficial, sem ligação com a Fórmula 1.
- **Fontes tipográficas** (licença SIL Open Font License, textos em `fontes/` e `carrossel/fontes/`):
  - IBM Plex Sans Condensed;
  - Archivo, Inter, Lexend, Outfit, Barlow Condensed e Bebas Neue, via Fontsource.

Análise de João Vitor Barberino.
