from dataclasses import dataclass
import os
from pathlib import Path
import shutil

@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    category: str
    description: str
    url: str = ''
    command: tuple = ()
    builtin: bool = True
    kind: str = "effect"

BUILTINS = [
    Entry('bonsai', 'Бонсай', 'Природа', 'Дерево постепенно вырастает из символов'),
    Entry('sakura', 'Сакура', 'Природа', 'Цветущая сакура и падающие лепестки'),
    Entry('aquarium', 'Аквариум', 'Природа', 'Рыбки, водоросли и пузырьки'),
    Entry('snow', 'Снег', 'Природа', 'Тихий снегопад'),
    Entry('rain', 'Дождь', 'Природа', 'Дождь и расходящиеся капли'),
    Entry('lava', 'Лавовая лампа', 'Абстракции', 'Плавающие и сливающиеся цветные пятна'),
    Entry('particles', 'Потоки частиц', 'Абстракции', 'Плавные течения из точек Брайля'),
    Entry('plasma', 'Плазма', 'Абстракции', 'Переливы цветных синусоидальных волн'),
    Entry('fire', 'Огонь', 'Абстракции', 'Колышущееся пламя'),
    Entry('fireworks', 'Фейерверк', 'Абстракции', 'Разлетающиеся цветные искры'),
    Entry('life', 'Игра «Жизнь»', 'Абстракции', 'Клеточный автомат Конвея'),
    Entry('pipes', 'Трубы', 'Ретро', 'Разноцветные трубы, растущие по экрану'),
    Entry('matrix', 'Матрица', 'Ретро', 'Зелёный цифровой дождь'),
    Entry('stars', 'Звёздный полёт', 'Космос', 'Полёт сквозь объёмное звёздное поле'),
    Entry('globe', 'Глобус', 'Космос', 'Вращающаяся Земля с условными контурами материков'),
    Entry('clock', 'Часы', 'Часы', 'Крупные цифровые часы и дата'),
    Entry('donut', 'Пончик 3D', 'Ретро', 'Вращающийся ASCII-тор'),
    Entry('dvd', 'DVD', 'Ретро', 'Отскакивающая от краёв надпись'),
    Entry('spectrum', 'Спектр · демо', 'Музыка', 'Декоративная анимация спектра; реальное аудио — через CAVA'),
    Entry('aurora', 'Северное сияние', 'Природа', 'Переливающиеся световые занавесы'),
    Entry('galaxy', 'Спиральная галактика', 'Космос', 'Рукава галактики из разноцветных точек'),
    Entry('blackhole', 'Чёрная дыра', 'Космос', 'Вращающийся аккреционный диск'),
    Entry('ocean', 'Океан', 'Природа', 'Набегающие морские волны'),
    Entry('ripple', 'Круги на воде', 'Природа', 'Расходящаяся рябь'),
    Entry('tunnel', 'Неоновый туннель', 'Ретро', 'Полёт через цветные рамки'),
    Entry('terrain', 'Ландшафт', 'Ретро', 'Движущийся трёхмерный рельеф из точек'),
    Entry('dna', 'ДНК', 'Абстракции', 'Вращающаяся двойная спираль'),
    Entry('lissajous', 'Кривые Лиссажу', 'Абстракции', 'Переплетение гармонических колебаний'),
    Entry('lorenz', 'Аттрактор Лоренца', 'Абстракции', 'Объёмная траектория хаотической системы'),
    Entry('pendulum', 'Маятниковая волна', 'Абстракции', 'Маятники с разными периодами'),
    Entry('kaleidoscope', 'Калейдоскоп', 'Абстракции', 'Симметричные меняющиеся узоры'),
    Entry('lightning', 'Молнии', 'Природа', 'Ветвящиеся электрические разряды'),
    Entry('bubbles', 'Пузырьки', 'Природа', 'Поднимающиеся воздушные пузырьки'),
    Entry('fireflies', 'Светлячки', 'Природа', 'Мерцающие огоньки в темноте'),
    Entry('orbit', 'Орбиты', 'Космос', 'Планеты вокруг звезды'),
    Entry('radar', 'Радар', 'Ретро', 'Вращающийся луч и появляющиеся отметки'),
    Entry('boids', 'Стая', 'Природа', 'Агенты держатся вместе и избегают столкновений'),
    Entry('maze', 'Лабиринт', 'Ретро', 'Постепенное построение лабиринта'),
    Entry('mandelbrot', 'Множество Мандельброта', 'Фракталы', 'Фрактал с анимированной палитрой'),
    Entry('julia', 'Множество Жюлиа', 'Фракталы', 'Плавно изменяющийся комплексный фрактал'),
    Entry('rings', 'Пульсирующие кольца', 'Абстракции', 'Концентрические круги из точек'),
    Entry('rose', 'Полярная роза', 'Абстракции', 'Вращающийся математический цветок'),
    Entry('rainbows', 'Радужные арки', 'Абстракции', 'Перекатывающиеся цветные дуги'),
    Entry('nebula', 'Туманность', 'Космос', 'Облака звёздной пыли из цветных частиц'),
    Entry('pulsar', 'Пульсар', 'Космос', 'Вращающиеся лучи нейтронной звезды'),
    Entry('comet', 'Комета', 'Космос', 'Яркое ядро и длинный рассыпающийся хвост'),
    Entry('meteors', 'Метеорный дождь', 'Космос', 'Летящие звёзды с затухающими следами'),
    Entry('saturn', 'Сатурн', 'Космос', 'Планета с наклонённой системой колец'),
    Entry('wormhole', 'Червоточина', 'Космос', 'Полёт через искривлённый звёздный тоннель'),
    Entry('startrails', 'Звёздные треки', 'Космос', 'Длинные дуги вращающегося неба'),
    Entry('moon', 'Фазы Луны', 'Космос', 'Меняющееся освещение лунного диска'),
    Entry('eclipse', 'Затмение', 'Космос', 'Тёмный диск и солнечная корона'),
    Entry('supernova', 'Сверхновая', 'Космос', 'Расширяющееся облако звёздного взрыва'),
    Entry('clouds', 'Облака', 'Природа', 'Мягкие слои плывущих облаков'),
    Entry('waterfall', 'Водопад', 'Природа', 'Вертикальные струи и брызги воды'),
    Entry('autumn', 'Листопад', 'Природа', 'Золотые и рыжие листья на ветру'),
    Entry('meadow', 'Цветущий луг', 'Природа', 'Покачивающаяся трава и цветы'),
    Entry('forest', 'Ночной лес', 'Природа', 'Силуэты хвойных деревьев'),
    Entry('rainwindow', 'Дождь за окном', 'Природа', 'Струйки на стекле и оконная рама'),
    Entry('campfire', 'Костёр', 'Природа', 'Пламя над поленьями под ночным небом'),
    Entry('jellyfish', 'Медузы', 'Природа', 'Пульсирующие купола и плавные щупальца'),
    Entry('butterflies', 'Бабочки', 'Природа', 'Парящие разноцветные крылья'),
    Entry('flowers', 'Сад цветов', 'Природа', 'Вращающиеся геометрические соцветия'),
    Entry('coral', 'Коралловый риф', 'Природа', 'Разветвлённые колышущиеся кораллы'),
    Entry('sand', 'Песчаные дюны', 'Частицы', 'Волны песка и летящие песчинки'),
    Entry('fountain', 'Фонтан', 'Частицы', 'Параболические струи водяных частиц'),
    Entry('sparks', 'Искры', 'Частицы', 'Горящие частицы с гравитацией'),
    Entry('magnets', 'Магнитное поле', 'Частицы', 'Силовые линии движущегося диполя'),
    Entry('vortex', 'Вихрь', 'Частицы', 'Частицы закручиваются к центру'),
    Entry('fluid', 'Течение', 'Частицы', 'Потоки частиц в меняющемся поле'),
    Entry('smoke', 'Дым', 'Частицы', 'Расширяющийся клубящийся шлейф'),
    Entry('diffusion', 'Диффузные узоры', 'Частицы', 'Извилистые полосы и ячеистые структуры'),
    Entry('explosion', 'Взрыв частиц', 'Частицы', 'Волна искр с замедляющимся расширением'),
    Entry('cube', 'Вращающийся куб', 'Геометрия', 'Объёмный каркас в перспективе'),
    Entry('tesseract', 'Тессеракт', 'Геометрия', 'Проекция вращения четырёхмерного куба'),
    Entry('sphere', 'Каркасная сфера', 'Геометрия', 'Параллели и меридианы объёмной сферы'),
    Entry('torusknot', 'Тороидальный узел', 'Геометрия', 'Замкнутая трёхмерная кривая'),
    Entry('mobius', 'Лента Мёбиуса', 'Геометрия', 'Перекрученная односторонняя поверхность'),
    Entry('klein', 'Бутылка Клейна', 'Геометрия', 'Проекция замкнутой необычной поверхности'),
    Entry('helix', 'Пружина', 'Геометрия', 'Вращающаяся объёмная спираль'),
    Entry('superformula', 'Суперформула', 'Геометрия', 'Фигура плавно меняет число лепестков'),
    Entry('harmonograph', 'Гармонограф', 'Геометрия', 'Затухающие переплетённые колебания'),
    Entry('spirograph', 'Спирограф', 'Геометрия', 'Многолепестковые циклические кривые'),
    Entry('moire', 'Муар', 'Геометрия', 'Наложение двух систем концентрических полос'),
    Entry('interference', 'Интерференция', 'Геометрия', 'Волны от трёх перемещающихся источников'),
    Entry('checkerboard', 'Шахматная перспектива', 'Ретро', 'Уходящая вдаль клетчатая плоскость'),
    Entry('waves3d', 'Объёмные волны', 'Геометрия', 'Волнистая сетчатая поверхность'),
    Entry('quasicrystal', 'Квазикристалл', 'Геометрия', 'Пятилучевые интерференционные орнаменты'),
    Entry('vectorgrid', 'Поле векторов', 'Геометрия', 'Поворачивающиеся стрелки поля'),
    Entry('sierpinski', 'Треугольник Серпинского', 'Фракталы', 'Фрактал методом хаотической игры'),
    Entry('fern', 'Папоротник Барнсли', 'Фракталы', 'Сложный лист из простых преобразований'),
    Entry('dragon', 'Кривая дракона', 'Фракталы', 'Рекурсивно сложенная фрактальная кривая'),
    Entry('hilbert', 'Кривая Гильберта', 'Фракталы', 'Постепенно заполняющая плоскость линия'),
    Entry('koch', 'Снежинка Коха', 'Фракталы', 'Вращающийся рекурсивный снежный контур'),
    Entry('burningship', 'Горящий корабль', 'Фракталы', 'Разветвлённый комплексный фрактал'),
    Entry('newton', 'Бассейны Ньютона', 'Фракталы', 'Области сходимости к трём корням'),
    Entry('apollonian', 'Аполлониевы узоры', 'Фракталы', 'Инверсии порождают вложенные круговые структуры'),
    Entry('reaction', 'Реакционные пятна', 'Фракталы', 'Диффузия и нелинейный рост ячеистых пятен'),
    Entry('pacman', 'Пакман · заставка', 'Ретро', 'Персонаж ест точки и убегает от призрака'),
    Entry('pong', 'Понг · заставка', 'Ретро', 'Шар и две движущиеся ракетки'),
    Entry('invaders', 'Космические захватчики', 'Ретро', 'Ряды пришельцев и стреляющий корабль'),
    Entry('snake', 'Змейка · заставка', 'Ретро', 'Змейка путешествует по экрану'),
    Entry('sinescroller', 'Синусный скроллер', 'Ретро', 'Волнистая строка в стиле демосцены'),
    Entry('maze3d', 'Трёхмерный коридор', 'Ретро', 'Движение через рамки в перспективе'),
    Entry('toasters', 'Летающие тостеры', 'Ретро', 'Крылатые тостеры из старых заставок'),
    Entry('tron', 'Световые трассы', 'Ретро', 'Цветные линии оставляют световой след'),
    Entry('skyline', 'Ночной город', 'Ретро', 'Силуэты домов и мерцающие окна'),
    Entry('doublependulum', 'Двойной маятник · узор', 'Аттракторы', 'Связанные колебания с затухающим следом'),
    Entry('rossler', 'Аттрактор Рёсслера', 'Аттракторы', 'Траектория трёхмерной хаотической системы'),
    Entry('clifford', 'Аттрактор Клиффорда', 'Аттракторы', 'Плотные крылья нелинейного отображения'),
    Entry('dejong', 'Аттрактор де Йонга', 'Аттракторы', 'Переплетённые хаотические облака'),
    Entry('ikeda', 'Аттрактор Икеды', 'Аттракторы', 'Узор дискретной нелинейной системы'),
    Entry('light_ribbons', 'Световые ленты', 'Световые скульптуры', 'Плавно изгибающиеся ленты в объёме'),
    Entry('light_gyroscope', 'Гироскоп света', 'Световые скульптуры', 'Вложенные кольца с независимым наклоном'),
    Entry('light_silk', 'Шёлковые волны', 'Световые скульптуры', 'Тонкие складки колышущейся поверхности'),
    Entry('light_bloom', 'Световой цветок', 'Световые скульптуры', 'Объёмная розетка из тонких лепестков'),
    Entry('light_gyroid', 'Гироид', 'Световые скульптуры', 'Волнистая пространственная поверхность'),
    Entry('light_chladni', 'Фигуры Хладни', 'Световые скульптуры', 'Меняющиеся узловые линии резонанса'),
    Entry('light_orbits', 'Орбитальное плетение', 'Световые скульптуры', 'Переплетённые кольцевые нити'),
    Entry('light_resonance', 'Резонансная чаша', 'Световые скульптуры', 'Круговая волна на вращающейся поверхности'),
    Entry('hopf_fibers', 'Расслоение Хопфа', 'Генеративное искусство', 'Переплетённые объёмные кольца'),
    Entry('nautilus_shell', 'Раковина наутилуса', 'Генеративное искусство', 'Вращающаяся логарифмическая раковина'),
    Entry('luminous_heart', 'Световое сердце', 'Генеративное искусство', 'Пульсирующий объёмный контур'),
    Entry('iris_filaments', 'Радужная диафрагма', 'Генеративное искусство', 'Радиальные световые нити'),
    Entry('dune_contours', 'Контуры дюн', 'Генеративное искусство', 'Медленно плывущий рельеф из линий'),
    Entry('porcelain', 'Фарфоровый сосуд', 'Генеративное искусство', 'Меняющийся профиль вращения'),
    Entry('nested_helix', 'Спиральное гнездо', 'Генеративное искусство', 'Три переплетённых кольцевых витка'),
    Entry('phyllotaxis', 'Филлотаксис', 'Генеративное искусство', 'Золотоугольная спираль точек'),
    Entry('fractal_flame', 'Фрактальное пламя', 'Генеративное искусство', 'Нелинейная система преобразований'),
    Entry('water_caustics', 'Подводный свет', 'Генеративное искусство', 'Блики пересекающихся водных волн'),
]

from .gallery_effects import REGISTRY as GALLERY
BUILTINS += [Entry(key,title,category,description) for key,title,category,description,family in GALLERY]

def ext(id, title, category, desc, repo, *command):
    return Entry(id, title, category, desc, 'https://github.com/' + repo, command, False, 'external')

SYSTEM_TOOLS = [
    Entry('performance', 'Производительность', 'Systems Things', 'CPU, память, swap, графики и отдельный журнал', kind='tool'),
    Entry('network', 'Состояние сети', 'Systems Things', 'Интерфейсы, скорости, ошибки, потери и журнал', kind='tool'),
    Entry('disk-io', 'Нагрузка дисков', 'Systems Things', 'Чтение/запись, IOPS, время активности и журнал', kind='tool'),
    Entry('disk-space', 'Место на дисках', 'Systems Things', 'Занято, свободно и полосы заполнения', kind='tool'),
    Entry('processes', 'Процессы', 'Systems Things', 'CPU и память процессов в реальном времени', kind='tool'),
    Entry('calendar', 'Календарь', 'Systems Things', 'Месяцы, вид года, подсветка сегодняшней даты', kind='tool'),
    Entry('system-info', 'О системе', 'Systems Things', 'Автономная сводка ОС и автоматически выбранный 3D-логотип', kind='tool'),
    Entry('sensors', 'Датчики и батарея', 'Systems Things', 'Температуры и состояние аккумулятора', kind='tool'),
    Entry('stopwatch', 'Секундомер', 'Systems Things', 'Пауза, круги и сброс', kind='tool'),
    Entry('timezones', 'Мировые часы', 'Systems Things', 'Часы с учётом часовых поясов', kind='tool'),
    Entry('journals', 'Журналы', 'Systems Things', 'Отдельная история производительности, сети и дисков', kind='tool'),
]

from .system_utilities import TOOLS as UTILITY_TOOLS
SYSTEM_TOOLS += [Entry(key,title,'Systems Things',description,kind='tool') for key,title,description in UTILITY_TOOLS]

EXTERNAL = [
    ext('cbonsai', 'cbonsai', 'Природа', 'Оригинальный генератор бонсая', 'jakobrees/cbonsai', 'cbonsai', '-l'),
    ext('csakura', 'csakura', 'Природа', 'Оригинальная сакура', 'realstrawhat/csakura', 'csakura'),
    ext('asciiquarium', 'asciiquarium', 'Природа', 'Классический ASCII-аквариум', 'cmatsuoka/asciiquarium', 'asciiquarium'),
    ext('snowmachine', 'snowmachine', 'Природа', 'Снегопад в терминале', 'sontek/snowmachine', 'snowmachine'),
    ext('metrocity', 'Metrocity', 'Природа', 'Пиксельные городские сценки; нужен Kitty graphics', 'Itz-Agasta/metrocity', 'metrocity'),
    ext('lavat', 'lavat', 'Абстракции', 'Оригинальная лавовая лампа', 'AngelJumbo/lavat', 'lavat'),
    ext('termflix', 'termflix', 'Абстракции', 'Набор процедурных анимаций', 'paulrobello/termflix', 'termflix'),
    ext('cbeams', 'cbeams', 'Абстракции', 'Цветные анимированные круги', 'tartley/cbeams', 'cbeams'),
    ext('fresco', 'fresco', 'Абстракции', 'Генеративные анимации', 'ZviBaratz/fresco', 'fresco'),
    ext('termart', 'termart', 'Абстракции', 'Бонсай, плазма, кривые', 'pknull/termart', 'termart'),
    ext('terminal-screensavers', 'terminal-screensavers', 'Сборники', 'Коллекция терминальных заставок', 'evantahler/terminal-screensavers'),
    ext('pipes.sh', 'pipes.sh', 'Ретро', 'Классические растущие трубы', 'pipeseroni/pipes.sh', 'pipes.sh'),
    ext('rxpipes', 'rxpipes', 'Ретро', 'Трубы на Rust', 'inunix3/rxpipes', 'rxpipes'),
    ext('cmatrix', 'cmatrix', 'Ретро', 'Классическая матрица', 'abishekvashok/cmatrix', 'cmatrix'),
    ext('gh-screensaver', 'gh-screensaver', 'Сборники', 'Расширение GitHub CLI', 'vilmibm/gh-screensaver', 'gh', 'screensaver'),
    ext('tanim', 'tanim', 'Сборники', 'Процедурные пиксельные сценки', 'SantiagoSchez/tanim', 'tanim'),
    ext('cava', 'CAVA · реальное аудио', 'Музыка', 'Спектр системного звука; требуется настройка аудиобэкенда', 'karlstav/cava', 'cava'),
    ext('viz', 'viz', 'Музыка', 'Спектр с цветовыми градиентами', 'Venomseye/viz', 'viz'),
    ext('terminal-visualizer', 'Terminal Visualizer', 'Музыка', 'Разные стили аудиовизуализации', 'Jakubic769/Terminal-Visualizer', 'visualizer'),
    ext('mapscii', 'MapSCII', 'Карты', 'Настоящая интерактивная карта; нужен интернет', 'rastapasta/mapscii', 'mapscii'),
    ext('globe-cli', 'globe-cli', 'Космос', 'Интерактивный ASCII-глобус', 'adam-wier/globe', 'globe'),
    ext('ascii-earth', 'ascii-earth', 'Космос', 'Планеты и реальные текстуры', 'pluttan/ascii-earth', 'ascii-earth'),
    ext('ascii-globe', 'ascii-globe', 'Космос', 'Земля по реальным изображениям', 'sisiphamus/ascii-globe', 'ascii-globe'),
    ext('ttymap', 'ttymap', 'Карты', 'Карта со сценариями и слоями данных', 'Kohei-Wada/ttymap', 'ttymap'),
    ext('tmaps', 'tmaps', 'Карты', 'Карта OpenStreetMap с маршрутами', 'morellodev/tmaps', 'tmaps'),
    ext('tte', 'TerminalTextEffects', 'Текст', 'Движок анимации текста', 'ChrisBuilds/terminaltexteffects', 'tte'),
    ext('bangen', 'bangen', 'Текст', 'Анимированные большие надписи', 'programmersd21/bangen', 'bangen', 'TTHINGS', '--screensaver'),
    ext('terminal-fun', 'terminal-fun', 'Сборники', 'Запускатель классических эффектов', 'CastilloworksAi/terminal-fun', 'insta'),
    ext('ascii-live', 'ascii-live', 'Сборники', 'Коллекция сетевых ASCII-анимаций', 'hugomd/ascii-live'),
    ext('peaclock', 'peaclock', 'Часы', 'Часы, таймер, секундомер', 'octobanana/peaclock', 'peaclock'),
    ext('clock-rs', 'clock-rs', 'Часы', 'Настраиваемые цифровые часы', 'Oughie/clock-rs', 'clock-rs'),
    ext('clock-tui', 'clock-tui', 'Часы', 'Часы и обратный отсчёт', 'race604/clock-tui', 'tclock'),
    ext('arttime', 'arttime', 'Часы', 'Часы с ASCII-артом', 'poetaman/arttime', 'arttime'),
    ext('cool-retro-term', 'cool-retro-term', 'Ретро', 'Отдельный эмулятор ЭЛТ-терминала', 'Swordfish90/cool-retro-term', 'cool-retro-term'),
    ext('btop', 'btop', 'Мониторинг', 'Монитор CPU, RAM, сети, дисков и процессов', 'aristocratos/btop', 'btop'),
    ext('duf', 'duf', 'Мониторинг', 'Наглядная таблица занятого и свободного места', 'muesli/duf', 'duf'),
    ext('dust', 'dust', 'Мониторинг', 'Дерево занимающих место папок', 'bootandy/dust', 'dust'),
    Entry('ncdu', 'ncdu · только просмотр', 'Мониторинг', 'Интерактивный анализ места в папках без удаления', 'https://dev.yorhel.nl/ncdu', ('ncdu','-r'), False, 'external'),
    ext('gdu', 'gdu', 'Мониторинг', 'Быстрый анализ занятого места', 'dundee/gdu', 'gdu'),
    ext('fastfetch', 'fastfetch', 'Мониторинг', 'Красивая сводка о системе', 'fastfetch-cli/fastfetch', 'fastfetch'),
    ext('calcurse', 'calcurse', 'Органайзер', 'Терминальный календарь и планировщик', 'lfos/calcurse', 'calcurse'),
]
ENTRIES = BUILTINS + SYSTEM_TOOLS + EXTERNAL

def executable(entry):
    if not entry.command:
        return None
    name = entry.command[0]
    # Optional tools stay in user space, no changes to /usr or system packages.
    base = Path(os.environ.get('TTHINGS_TOOLS', Path.home() / '.local/share/tthings/tools'))
    for parent in (base / entry.id / 'bin', base / entry.id, Path.home() / '.local/bin'):
        for suffix in (('', '.exe') if os.name == 'nt' else ('',)):
            path = parent / (name + suffix)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
    if entry.id == 'gh-screensaver':
        # Presence of gh alone does not imply presence of its extension.
        return shutil.which('gh-screensaver')
    return shutil.which(name)

def search(query='', category='Все', mode='all'):
    q = query.casefold()
    return [e for e in ENTRIES if (category == 'Все' or category == e.category)
            and (mode == 'all' or (mode == 'builtin' and e.kind=='effect') or (mode == 'systems' and e.kind=='tool') or (mode == 'external' and not e.builtin))
            and q in f'{e.id} {e.title} {e.category} {e.description}'.casefold()]
