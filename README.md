# fips-pdf-parser

# Парсер патентов ФИПС

Программа ищет патенты по номерам в открытых реестрах ФИПС и сохраняет отрендеренные карточки документов в PDF. PDF создаётся через Microsoft Edge/Chrome так же, как печать страницы через `Ctrl+P`.

## Установка на Windows 10

1. Установите Python 3.11 или 3.12 с официального сайта: https://www.python.org/downloads/windows/
2. В установщике включите пункт `Add Python.exe to PATH`.
3. Откройте PowerShell и выполните:

```powershell
cd C:\parser\fips-pdf-parser
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Если PowerShell запрещает активацию окружения, выполните один раз:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Для сохранения PDF нужен установленный Microsoft Edge или Google Chrome.

## Запуск

```powershell
python -m pip install -r requirements.txt
python main.py
```

Откроется Windows-интерфейс. Выберите реестр, введите один или несколько номеров, выберите папку и нажмите «Найти и сохранить PDF».

Для печати нужен установленный Microsoft Edge или Google Chrome. При необходимости путь к браузеру можно задать переменной окружения `FIPS_BROWSER`.

Поддерживаются реестры:

- Изобретения
- Полезные модели
- Промышленные образцы
- Товарные знаки
- Программы для ЭВМ
- Географические указания и НМПТ
- Заявки на изобретения
- Заявки на товарные знаки

Для запуска без интерфейса:

```powershell
python main.py --cli --registry "Изобретения" --numbers "2799999 2800000" --output patents
```

Для защиты сервиса программа делает паузу 2 секунды между поисковыми запросами и 0,2 секунды между загрузками изображений. При ответах ФИПС `403`, `429` или `503` текущая операция останавливается и показывает причину, без попыток обходить ограничение.