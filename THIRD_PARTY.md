# Included components

| Component | Source | License / notices |
|---|---|---|
| tspotify | supplied clean handoff, commit b9de12e7124cdfc1b77753a09ab828e4e0885f26 | components/tspotify/source/LICENSE, NOTICE |
| TVPN | supplied local project 1.3.1 with install-only/lifecycle changes | components/tvpn/source/LICENSE, SOURCES.md, assets/licenses |
| tthings | supplied handoff 0.7.0 | components/tthings/source/LICENSE; Fastfetch notices shipped in source |
| ttelegram | supplied code allowlist 2026.11.18.4 | upstream tg Unlicense: components/ttelegram/source/vendor/TG-LICENSE.txt |
| tthings background renderers | earlier supplied handoff | ttools/visuals/LICENSE |

The ttools source adaptation to tspotify adds a Windows implementation of its
managed installation lock. The tthings InstanceLease adapter accepts
TTOOLS_TTHINGS_PREFIX so detached windows remain visible to the suite updater.
Its Windows CLI also selects UTF-8 for redirected Unicode/Braille output. Its license is preserved. The Telegram adapter contains
the author's tg/views.py patch and verifies the pinned original file before applying it.
Telegram runtime dependencies are distributed as unmodified wheels; each wheel
retains its own licenses. Spotify's optional streaming engine has separate notices
and checksum manifests supplied by the tspotify package.

No user venv, account configuration, credentials, message databases or logs are
included. The public Riseup CA certificate is application data, not a private key.

Нативный Windows preview ttelegram содержит отдельный fork python-telegram `2.0.0+ttnative.1`, TDLib 1.8.66 и Python embedded. Исходники fork и патча tg находятся в `components/ttelegram/windows-native/source/vendor/`, лицензии — в соседнем `licenses/`. Бинарная поставка и её происхождение описаны в HANDOFF.md и python-runtime-provenance.json. Linux-компонент не заменён.

В составе tthings обновлён чистый авторский снимок 0.7.2 (200 эффектов / 19 инструментов). Сохранены адаптации ttools: адресная блокировка окон через TTOOLS_TTHINGS_PREFIX и UTF-8 вывода на Windows. Новый лаунчер использует стабильный MIT renderer API, не присваивает себе авторство исходных эффектов.

В Windows-адаптере ttelegram добавлено отображение `_curses` на существующий VT backend: upstream `tg.views` импортирует тип window из `_curses` напрямую. Исходный архив по-прежнему проверяется по закреплённому SHA; затем применяются два явно перечисленных исправления из исходников репозитория и обновляется локальный файловый инвентарь. Второе исправление нормализует сравнение путей в тесте на Windows. Авторский архив не изменялся.
