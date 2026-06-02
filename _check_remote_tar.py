import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("104.225.159.174", username="root", password="C90zIbzODdHv", timeout=30)
_, o, _ = c.exec_command(
    "ls -lh /tmp/es_data.tar.gz 2>&1; ps aux | grep -E '[t]ar.*es8' || true; "
    "docker ps -a --filter name=elasticsearch8"
)
print(o.read().decode())
c.close()
