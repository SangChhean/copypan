import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("104.225.159.174", username="root", password="C90zIbzODdHv", timeout=30)
for cmd in [
    "ls -la /opt/copypan 2>/dev/null || echo NO_opt_copypan",
    "ls -la /opt/pansearch 2>/dev/null || echo NO_opt_pansearch",
    "docker ps -a --filter name=elastic --format '{{.Names}} {{.Status}}'",
    "docker inspect elasticsearch8 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' 2>/dev/null || true",
    "find /opt -maxdepth 3 -type d -name 'es_data' 2>/dev/null",
    "find /opt -maxdepth 3 -type d -name 'es8_data' 2>/dev/null",
]:
    print("===", cmd[:60], "===")
    _, o, e = c.exec_command(cmd)
    print(o.read().decode(errors="replace"))
    err = e.read().decode(errors="replace")
    if err.strip():
        print("stderr:", err)
c.close()
