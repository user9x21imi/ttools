@echo off
"%~dp0bootstrap\python.exe" -c "import runpy,sys;runpy.run_path(sys.argv.pop(1),run_name='__main__')" "%~dp0manage.py" launch %*
