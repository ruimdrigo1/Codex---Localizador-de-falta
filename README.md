# Localizador de Falta (COMTRADE) - Windows 11

Aplicação desktop profissional para engenharia de proteção, com foco em análise de distúrbios COMTRADE (`.cfg` + `.dat`) e suporte à identificação de falta com visão ANSI.

## Recursos implementados

- Leitura de arquivos COMTRADE (`CFG`/`DAT`).
- Visualização de curvas de onda (correntes de fase A/B/C).
- Cálculo de componentes simétricas (`I0`, `I1`, `I2`).
- Classificação de tipo de falta e fase provável.
- Painel de proteções ANSI com indicação de atuação estimada.
- Módulo dedicado de localização por sequência negativa (2 terminais), com entradas manuais de TERMINAL S/R, impedância total da LT, comprimento em km, V2/I2 na extremidade S e V2/I2 na extremidade R (conforme planilha de referência).
- Compatível com arquivos CFG em UTF-8, UTF-8 BOM, CP1252 e Latin-1 (fallback automático).
- Tratamento robusto para casos numéricos com discriminante negativo no método de sequência negativa (fallback sem interrupção do cálculo).
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
