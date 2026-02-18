# Localizador de Falta (COMTRADE) - Windows 11

Aplicação desktop profissional para engenharia de proteção, com foco em análise de distúrbios COMTRADE (`.cfg` + `.dat`) e suporte à identificação de falta com visão ANSI.

## Recursos implementados

- Leitura de arquivos COMTRADE (`CFG`/`DAT`).
- Visualização de curvas de onda (correntes de fase A/B/C).
- Cálculo de componentes simétricas (`I0`, `I1`, `I2`).
- Classificação de tipo de falta e fase provável.
- Painel de proteções ANSI com indicação de atuação estimada.
- Cálculo avançado da distância da falta por laço de impedância (estilo relé de distância): fase-terra com compensação residual (Z1/Z0), bifásica por laço fase-fase e trifásica por sequência positiva.
- Compatível com arquivos CFG em UTF-8, UTF-8 BOM, CP1252 e Latin-1 (fallback automático).
- Interface desktop em padrão profissional (PySide6 + gráficos).

## Requisitos

- Windows 11
- Python 3.11+

## Gerar executável `.exe`

No Windows, abra o terminal na pasta do projeto e execute:

```bat
build_windows.bat
```

O executável será gerado em:

```text
dist\LocalizadorDeFalta.exe
```

## Execução em modo desenvolvimento

```bash
pip install -r requirements.txt
python app.py
```

## Observações de engenharia

- A identificação de atuação ANSI é feita por regras elétricas heurísticas, pensadas para triagem rápida de oscilografias.
- Para aplicação em operação real, recomenda-se calibrar pickups por instalação, relação TC/TP e ajustes por relé/fabricante.
