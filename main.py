import typer, questionary, os, docker, time
from yaspin import yaspin

docker = docker.from_env()
app = typer.Typer()

def askPyVersion():
    return questionary.select(
        "Select a Python version",
        choices=[
            "3.9",
            "3.10",
            "3.11",
            "3.12",
            "3.13"
        ]).ask()


@app.command(name="create")
def create(name: str = typer.Argument(..., help="Name of the dev environment")):
    """
    Create a new dev env
    """
    Dockerfile = ""

    framework = questionary.select(
    "Select a framework",
    choices=[
        "Python",
        "Static HTML",
        "General Purpose"
    ]).ask()

    if framework == "Python":
        version = askPyVersion()
        Dockerfile += "FROM python:" + version + "\n"
        Dockerfile += "WORKDIR /app\n"
        pip_requirements = questionary.text("pip requirements? Enter a space-separated list of packages, filepath to a requirements.txt file, or leave empty for none.").ask()
        if pip_requirements:
            if os.path.isfile(pip_requirements):
                path = os.path.abspath(pip_requirements)
                Dockerfile += "COPY " + path + " /app/requirements.txt\n"
                Dockerfile += "RUN pip install -r requirements.txt\n"
            else:
                packages = pip_requirements.split()
                if packages:
                    Dockerfile += "RUN pip install " + " ".join(packages) + "\n"
  
    importDir = questionary.text("Import directory? Enter a path to the directory to import, or leave empty for none.").ask()
    if importDir:
        if os.path.isdir(importDir):
            path = os.path.abspath(importDir)
            Dockerfile += "COPY " + path + " /app/\n"
        else:
            typer.echo("Invalid directory path provided.")
            return
    
    features = questionary.checkbox(
        "Select features to include",
        choices=[
            "SSH",
            "Tailscale",
            "OpenVSCode Server",
            "Git",
        ]).ask()
    if features:
        if "SSH" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y openssh-server\n"
            Dockerfile += "RUN mkdir /var/run/sshd\n"
            Dockerfile += "RUN echo 'root:root' | chpasswd\n"
            Dockerfile += "RUN sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config\n"
            Dockerfile += "RUN sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config\n"
            Dockerfile += "EXPOSE 22\n"

        if "Tailscale" in features:
            Dockerfile += "RUN curl -fsSL https://tailscale.com/install.sh | sh\n"

        if "OpenVSCode Server" in features:
            Dockerfile += "RUN curl -fsSL https://code-server.dev/install.sh | sh\n"
            Dockerfile += "EXPOSE 8080\n"
            # Set up code-server config for no password and bind to 0.0.0.0
            Dockerfile += "RUN mkdir -p /root/.config/code-server && echo 'bind-addr: 0.0.0.0:8080\\nauth: none' > /root/.config/code-server/config.yaml\n"

        if "Git" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y git\n"

    typer.echo("Saving Dockerfile...")
    with open("Dockerfile", "w") as f:
        f.write(Dockerfile)
    typer.echo("Dockerfile created successfully.")

    with yaspin():
        typer.echo("Building Docker image...")
        image = docker.images.build(
            path=".",
            forcerm=True
        )
        imageId = image[0].id
        typer.echo(f"Docker image '{imageId}' created successfully.")

    typer.echo("Creating Docker container...")
    ports = {}
    if "SSH" in features:
        ports['22/tcp'] = None
    if "OpenVSCode Server" in features:
        ports['8080/tcp'] = None

    tailscale_cmd = ""
    if "Tailscale" in features:
        authKey = questionary.text("Enter your Tailscale auth key:").ask()
        if authKey:
            # Start tailscaled in background, then up, then exec the rest
            tailscale_cmd = f"tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --outbound-http-proxy-listen=localhost:1055 & sleep 2 && tailscale up --auth-key={authKey} && "
        else:
            typer.echo("No Tailscale auth key provided. Tailscale will not be configured.")

    main_cmds = []
    if "SSH" in features:
        main_cmds.append("/usr/sbin/sshd -D")
    if "OpenVSCode Server" in features:
        main_cmds.append("code-server")
    if not main_cmds:
        main_cmds.append("sleep infinity")

    # Join main commands with '&' to run in parallel, then wait
    parallel_cmd = " & ".join(main_cmds) + " & wait"

    # Prepend tailscale_cmd if needed
    full_cmd = f"{tailscale_cmd}{parallel_cmd}"

    cmd = ["sh", "-c", full_cmd]

    container = docker.containers.run(
        image=imageId,
        name=name,
        detach=True,
        auto_remove=True,
        command=cmd,
        ports=ports,
    )
    typer.echo(f"Docker container '{name}' created successfully.")
    if "SSH" in features or "OpenVSCode Server" in features or "Tailscale" in features:
        typer.echo("\nTo access the container, use the following commands:")
        container.reload()
        if "SSH" in features:
            typer.echo(f"ssh root@localhost -p {container.attrs['NetworkSettings']['Ports']['22/tcp'][0]['HostPort']}")
        if "OpenVSCode Server" in features:
            typer.echo(f"Open your browser and go to http://localhost:{container.attrs['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort']}")
        if "Tailscale" in features:
            typer.echo("Waiting for Tailscale to connect...")
            time.sleep(5)
            tailscale_ip = container.exec_run("tailscale ip -4")[1].decode().strip()
            typer.echo(f"Tailscale IP: {tailscale_ip}")

    if "SSH" in features:
        toSSH = questionary.confirm("Do you want to SSH into the container?").ask()
        if toSSH:
            os.system(f"ssh root@localhost -p {container.attrs['NetworkSettings']['Ports']['22/tcp'][0]['HostPort']}")

app()