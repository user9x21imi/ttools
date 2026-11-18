import argparse
import json
import os
import random
import sys
from . import __version__
from .catalog import BUILTINS,ENTRIES,SYSTEM_TOOLS


def main(argv=None):
    parser=argparse.ArgumentParser(description='tthings — автономный терминальный лаунчер анимаций')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--effect',choices=[e.id for e in BUILTINS])
    parser.add_argument('--snap',action='store_true',help='привязка выделения к границам окон (с --region)')
    parser.add_argument('--random',action='store_true',help='случайная встроенная анимация')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--tool',choices=[e.id for e in SYSTEM_TOOLS],help='инструмент Systems Things')
    group.add_argument('--window',action='store_true',help='отдельное окно')
    group.add_argument('--region',action='store_true',help='выделить область рабочего стола')
    group.add_argument('--apply-update',metavar='MANIFEST',help='применить проверяемый манифест в --prefix')
    group.add_argument('--rollback',action='store_true',help='откатить управляемую установку --prefix')
    group.add_argument('--stop-managed',action='store_true',help='штатно закрыть экземпляры в --prefix')
    group.add_argument('--install-info',action='store_true',help='JSON управляемой установки --prefix')
    group.add_argument('--install',action='store_true',help='установка в домашнюю папку без sudo')
    group.add_argument('--enable-hotkey',action='store_true')
    group.add_argument('--hotkey',action='store_true',help='обработчик глобальной комбинации клавиш')
    group.add_argument('--list',action='store_true')
    group.add_argument('--doctor',action='store_true')
    parser.add_argument('--prefix',help='отдельный пользовательский каталог управляемой установки')
    parser.add_argument('--with-hotkeys',action='store_true',help='явно включить горячие клавиши при обычной --install')
    parser.add_argument('--path',help='папка для анализа места (с --tool storage)')
    parser.add_argument('--once',action='store_true',help='один JSON-снимок мониторинга (с --tool)')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--fps',type=int,default=20)
    parser.add_argument('--duration',type=float,help='закрыть анимацию через N секунд')
    parser.add_argument('--geometry',help='размер окна, например 800x480+100+100')
    parser.add_argument('--snapshot',metavar='WIDTHxHEIGHT',help='текстовый кадр эффекта без терминала')
    args=parser.parse_args(argv)
    managed_operation=args.apply_update or args.rollback or args.stop_managed or args.install_info
    if managed_operation and not args.prefix:parser.error('Управляемая операция требует --prefix')
    if args.prefix and not (managed_operation or args.install):parser.error('--prefix используется только для установки/обновления/остановки')
    if args.with_hotkeys and (not args.install or args.prefix):parser.error('--with-hotkeys допустим только с обычной --install без --prefix')
    if args.once and not args.tool:parser.error('--once требует --tool')
    if args.path and args.tool!='storage':parser.error('--path используется с --tool storage')
    if args.snap and not args.region:parser.error('--snap используется вместе с --region')
    if not 1<=args.fps<=60:parser.error('--fps: от 1 до 60')
    if args.duration is not None and args.duration<=0:parser.error('--duration должен быть больше нуля')
    if args.geometry:
        import re
        if not re.fullmatch(r'[1-9][0-9]{0,4}x[1-9][0-9]{0,4}(?:[+-][0-9]+[+-][0-9]+)?',args.geometry):
            parser.error('--geometry: WIDTHxHEIGHT или WIDTHxHEIGHT+X+Y')
    from .deployment import InstanceLease
    lease=InstanceLease()
    try:
        if managed_operation:
            from .deployment import apply_update,rollback,stop_managed,read_metadata
            result=apply_update(args.apply_update,args.prefix) if args.apply_update else rollback(args.prefix) if args.rollback else stop_managed(args.prefix) if args.stop_managed else read_metadata(args.prefix)
            print(json.dumps(result,ensure_ascii=False));return 0
        if args.install and args.prefix:
            from .deployment import install_current
            print(json.dumps(install_current(args.prefix),ensure_ascii=False));return 0
        if args.install:
            from .install import install
            install(with_hotkeys=args.with_hotkeys);return 0
        if args.enable_hotkey:
            from .install import enable_hotkey
            enable_hotkey();return 0
        if args.hotkey:
            from .hotkeys import listen
            listen();return 0
        if args.list:
            if args.json:
                import dataclasses
                print(json.dumps([dataclasses.asdict(e) for e in ENTRIES],ensure_ascii=False,indent=2))
            else:
                for e in ENTRIES:print(f'{e.id:24} {"встроен" if e.builtin else "внешний":9} {e.title}')
            return 0
        if args.doctor:
            import platform,importlib.util
            print('tthings',__version__)
            print('Система:',platform.platform())
            print('Терминал:',sys.stdout.isatty())
            print('Оконный модуль Tk:',bool(importlib.util.find_spec('tkinter')))
            print('Сеанс:',os.environ.get('XDG_SESSION_TYPE',sys.platform))
            print('Встроенных эффектов:',len(BUILTINS))
            print('Системных инструментов:',len(SYSTEM_TOOLS))
            print('Оригиналы в каталоге:',sum(not e.builtin for e in ENTRIES))
            print('Оконный режим требует графического сеанса. Внешние инструменты устанавливаются отдельно.')
            return 0
        if not (args.snapshot or args.once):lease.start()
        if args.tool and args.once:
            from .system_ui import MONITORS,monitor_snapshot
            if args.tool not in MONITORS:parser.error('--once доступен для performance, network, disk-io, disk-space, processes, sensors')
            print(json.dumps(monitor_snapshot(args.tool),ensure_ascii=False,indent=2,allow_nan=False));return 0
        if args.tool:
            if not sys.stdin.isatty() or not sys.stdout.isatty():parser.error('Для инструмента нужен терминал; для данных мониторинга используйте --once')
            from .system_ui import run_tool
            from .terminal import Terminal
            with Terminal() as term:run_tool(term,args.tool,path=args.path,duration_limit=args.duration)
            return 0
        if args.snapshot:
            from .effects import Scene
            try:w,h=map(int,args.snapshot.lower().split('x'))
            except ValueError:parser.error('Размер: WIDTHxHEIGHT, например 80x24')
            if not 1<=w<=300 or not 1<=h<=140:parser.error('Размер кадра: 1..300 x 1..140')
            print(Scene(args.effect or 'bonsai',seed=42).render(w,h,12).plain());return 0
        effect=args.effect or (random.choice(BUILTINS).id if args.random else None)
        if args.region or args.window:
            from .gui import show
            show(effect,args.region,args.geometry,args.duration,snap=args.snap);return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            parser.error('Нужен интерактивный терминал. Используйте --list, --snapshot или --window.')
        if effect:
            from .app import play
            from .terminal import Terminal
            with Terminal() as term:play(term,effect,fps=args.fps,duration=args.duration)
        else:
            from .app import run
            run()
    except (KeyboardInterrupt,EOFError):return 0
    except (OSError,RuntimeError,ValueError) as exc:
        print(f'tthings: {exc}',file=sys.stderr);return 1
    finally:lease.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
