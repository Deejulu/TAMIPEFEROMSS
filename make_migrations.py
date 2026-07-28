import subprocess
import sys

proc = subprocess.Popen(
    [sys.executable, 'manage.py', 'makemigrations', 'accounts'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
# Option 1, then provide Python string literal as default
stdout, stderr = proc.communicate(input='1\n"temp_user"\n')
print('STDOUT:', stdout)
print('STDERR:', stderr)
print('Return code:', proc.returncode)
