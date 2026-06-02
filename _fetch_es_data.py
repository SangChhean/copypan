# One-off: stop remote ES, tar es8_data, download (do not commit)
import sys
import paramiko

HOST = "104.225.159.174"
USER = "root"
PASSWORD = "C90zIbzODdHv"
REMOTE_TAR = "/tmp/es_data.tar.gz"
LOCAL_TAR = r"E:\copypan\es_data.tar.gz"


def run(client, cmd, timeout=3600):
    print(f">>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip(), file=sys.stderr)
    return exit_code, out, err


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    print("Stopping remote elasticsearch8...")
    code, _, _ = run(client, "docker stop elasticsearch8")
    if code != 0:
        print("Warning: docker stop returned", code, file=sys.stderr)

    print("Creating archive (es8_data on server)...")
    code, out, err = run(
        client,
        "cd /opt/copypan && rm -f /tmp/es_data.tar.gz && tar czf /tmp/es_data.tar.gz es8_data && ls -lh /tmp/es_data.tar.gz",
        timeout=7200,
    )
    if code != 0:
        print(f"Remote tar failed exit={code}", file=sys.stderr)
        run(client, "docker start elasticsearch8")
        sys.exit(code)

    print("Restarting remote elasticsearch8...")
    run(client, "docker start elasticsearch8")

    print("Downloading via SFTP (may take a while)...")
    sftp = client.open_sftp()

    def progress(transferred, total):
        if total and transferred % (50 * 1024 * 1024) < 65536:
            pct = 100.0 * transferred / total
            print(f"  {transferred // (1024 * 1024)} / {total // (1024 * 1024)} MB ({pct:.1f}%)")

    sftp.get(REMOTE_TAR, LOCAL_TAR, callback=progress)
    sftp.close()
    client.close()
    print(f"Saved to {LOCAL_TAR}")


if __name__ == "__main__":
    main()
