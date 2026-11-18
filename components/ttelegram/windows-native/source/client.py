"""Local QR-first entry point; keeps the upstream client unchanged."""
from tg import config
from tg import tdlib
from tg import __main__ as app
import qrcode
import getpass
import subprocess
import sys
from telegram.client import AuthorizationState
from workspace_mode import set_mode


class LoginRetry(Exception):
    """The native client cannot be reused; retry in a fresh process."""


def print_qr(link):
    set_mode('Вход по QR · сканируйте код телефоном')
    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(link); qr.make(fit=True)
    matrix = qr.get_matrix()
    print('\033[2J\033[H\033[1;36mTELEGRAM / ВХОД ПО QR\033[0m\n')
    print('На телефоне: Telegram → Настройки → Устройства → Подключить устройство\n')
    # Explicit black/white colors keep the QR readable with every terminal palette.
    for y in range(0, len(matrix), 2):
        row = ''
        for x in range(len(matrix)):
            upper = matrix[y][x]
            lower = matrix[y+1][x] if y+1 < len(matrix) else False
            fg = '0;0;0' if upper else '255;255;255'
            bg = '0;0;0' if lower else '255;255;255'
            row += f'\033[38;2;{fg}m\033[48;2;{bg}m▀'
        print(row+'\033[0m')
    print('\nОжидаю сканирования. QR обновляется автоматически.', flush=True)


class QrTdlib(tdlib.Tdlib):
    def login_interactive(self):
        terminal_states = {
            AuthorizationState.CLOSED, AuthorizationState.CLOSING,
            AuthorizationState.LOGGING_OUT, AuthorizationState.UNKNOWN,
        }
        try:
            if self.authorization_state in terminal_states:
                raise LoginRetry()
            state = self.login(blocking=False)
            while state != AuthorizationState.READY:
                if state in terminal_states:
                    raise LoginRetry()
                state = self._login_step(state)
        except (RuntimeError, TimeoutError) as error:
            if 'lock' in str(error).lower():
                raise SystemExit('Telegram уже открыт другим процессом. Закройте второй клиент.') from error
            # Never re-enter login() on a failed native client: CLOSED cannot recover.
            raise LoginRetry() from error

    def _login_step(self, state):
        if state == AuthorizationState.WAIT_PASSWORD:
            set_mode('Вход · введите облачный пароль Telegram')
            print('\033[2J\033[H\033[1;36mTELEGRAM / ДВУХЭТАПНАЯ ПРОВЕРКА\033[0m\n')
            print('QR-код принят. Для завершения входа нужен облачный пароль Telegram.')
            print('\n\033[1;93m+------------------------------------------+\n|  Введите облачный пароль Telegram        |\n+------------------------------------------+\033[0m\n')
            print('Это пароль из настроек двухэтапной проверки, а не код из SMS.')
            print('При вводе символы не отображаются — это нормально.\n', flush=True)
            while True:
                password = getpass.getpass('\033[1;93mВведите облачный пароль: \033[0m')
                if not password:
                    print('Введите пароль для продолжения входа.', flush=True)
                    continue
                try:
                    return self.send_password(password)
                except RuntimeError as error:
                    if 'PASSWORD_HASH_INVALID' not in str(error):
                        raise
                    print('Неверный пароль. Попробуйте ещё раз.', flush=True)
                finally:
                    password = None
        return super()._login_step(state)

    def _send_phone_number_or_bot_token(self):
        # Called only after TDLib has accepted parameters and is waiting for login.
        return self.login_with_qr(request=True)


def run_client():
    from features import install
    install()
    from composer import install as install_composer
    install_composer()
    from media import install as install_media
    install_media()
    from mouse_ui import install as install_mouse
    install_mouse()
    from workspace_mode import install_handlers
    install_handlers()
    from recovery import install as install_recovery
    install_recovery()
    from engine import install as install_engine
    install_engine()
    tdlib.print_qr = print_qr
    app.Tdlib = QrTdlib
    # The Python wrapper requires a nonempty phone field at construction time.
    # This marker is never sent: the phone action above requests QR authentication.
    # The same explicit files directory preserves an existing authorized session.
    config.ensure_phone = lambda: config.PHONE or 'qr-login'
    try:import termios
    except ImportError:termios=None
    keyboard=None
    try:
        if termios is not None and sys.stdin.isatty():
            keyboard=termios.tcgetattr(sys.stdin)
            active=list(keyboard);active[0]&=~(termios.IXON|termios.IXOFF)
            termios.tcsetattr(sys.stdin,termios.TCSANOW,active)
        app.run_tui()
    finally:
        if keyboard is not None:
            try:termios.tcsetattr(sys.stdin,termios.TCSANOW,keyboard)
            except (termios.error,OSError):pass


def main():
    if '--worker' in sys.argv[1:]:
        try:
            run_client()
        except LoginRetry:
            # The process exits before another TDLib instance opens the same database.
            raise SystemExit(75)
        return
    while True:
        result = subprocess.run([sys.executable, __file__, '--worker'])
        if result.returncode != 75:
            import os
            if result.returncode==0 and os.environ.get('TMUX','').split(',')[0].endswith('/'+__import__('runtime').SOCKET):
                subprocess.run(['tmux','kill-session','-t','telegram'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return result.returncode
        set_mode('Ошибка входа · Enter — новая попытка')
        print('\033[2J\033[H\033[1;93mTELEGRAM / ПОВТОРНЫЙ ВХОД\033[0m\n')
        print('Не удалось завершить вход: соединение авторизации закрыто или прервано.')
        print('Можно попробовать снова. Сохранённые данные аккаунта не удаляются.\n')
        try:
            answer = input('\033[1;93mEnter — новая попытка входа, q — выйти: \033[0m').strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if answer == 'q':
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
