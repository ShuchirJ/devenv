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
        "General Purpose"
    ]).ask()

    if not framework: exit(0)

    if framework == "Python":
        version = askPyVersion()
        if version is None: exit(0)
        Dockerfile += "FROM python:" + version + "\n"
        Dockerfile += "WORKDIR /app\n"
        pip_requirements = questionary.text("pip requirements? Enter a space-separated list of packages, filepath to a requirements.txt file, or leave empty for none.").ask()
        if pip_requirements == None: exit(0)

        if pip_requirements:
            if os.path.isfile(pip_requirements):
                path = pip_requirements
                Dockerfile += "COPY " + path + " /app/requirements.txt\n"
                Dockerfile += "RUN pip install -r requirements.txt\n"
            else:
                packages = pip_requirements.split()
                if packages:
                    Dockerfile += "RUN pip install " + " ".join(packages) + "\n"
  
    elif framework == "General Purpose":
        Dockerfile += "FROM debian:bookworm-slim" + "\n"
        Dockerfile += "WORKDIR /app\n"

    importDir = questionary.text("Import directory? Enter a path to the directory to import, or leave empty for none.").ask()
    if importDir is None: exit(0)
    if importDir:
        if os.path.isdir(importDir):
            path = importDir
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
            "Curl",
            "Wget", 
            "Nano"
        ]).ask()
    if features is None: exit(0)

    if features:
        if "SSH" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y openssh-server\n"
            Dockerfile += "RUN mkdir /var/run/sshd\n"
            Dockerfile += "RUN echo 'root:root' | chpasswd\n"
            Dockerfile += "RUN sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config\n"
            Dockerfile += "RUN sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config\n"
            Dockerfile += "EXPOSE 22\n"

        if "Tailscale" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y curl\n"
            Dockerfile += "RUN curl -fsSL https://tailscale.com/install.sh | sh\n"

        if "OpenVSCode Server" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y curl\n"
            Dockerfile += "RUN curl -fsSL https://code-server.dev/install.sh | sh\n"
            Dockerfile += "EXPOSE 8080\n"
            # Set up code-server config for no password and bind to 0.0.0.0
            Dockerfile += "RUN mkdir -p /root/.config/code-server && echo 'bind-addr: 0.0.0.0:8080\\nauth: none' > /root/.config/code-server/config.yaml\n"

        if "Git" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y git\n"

        if "Curl" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y curl\n"

        if "Wget" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y wget\n"

        if "Nano" in features:
            Dockerfile += "RUN apt-get update && apt-get install -y nano\n"

    databases = questionary.checkbox(
        "Select databases to include",
        choices=[
            "MongoDB"
        ]).ask()
    if databases is None: exit(0)

    if databases:
        if "MongoDB" in databases:
            Dockerfile += "RUN apt-get update && apt-get install -y gnupg curl\n"
            Dockerfile += "RUN curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor\n"
            Dockerfile += 'RUN echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/8.0 main" | tee /etc/apt/sources.list.d/mongodb-org-8.0.list\n'
            Dockerfile += "RUN apt-get update && apt-get install -y mongodb-org\n"
            Dockerfile += "RUN mkdir -p /data/db\n"
            Dockerfile += "RUN chown -R mongodb:mongodb /data/db\n"
            Dockerfile += "RUN mkdir -p /var/lib/mongodb\n"
            Dockerfile += "RUN chown -R mongodb:mongodb /var/lib/mongodb\n"
            Dockerfile += "RUN mkdir -p /var/log/mongodb\n"
            Dockerfile += "RUN chown -R mongodb:mongodb /var/log/mongodb\n"
            Dockerfile += "EXPOSE 27017\n"

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
    if "MongoDB" in databases:
        ports['27017/tcp'] = None

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
    if "MongoDB" in databases:
        main_cmds.append("mongod --bind_ip_all")
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
        labels={"dev_env": "true"},
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

    if "MongoDB" in databases:
        container.reload()
        typer.echo(f"MongoDB is running on system port {container.attrs['NetworkSettings']['Ports']['27017/tcp'][0]['HostPort']}")

    if "SSH" in features:
        toSSH = questionary.confirm("Do you want to SSH into the container?").ask()
        if toSSH:
            os.system(f"ssh root@localhost -p {container.attrs['NetworkSettings']['Ports']['22/tcp'][0]['HostPort']}")


@app.command(name="info")
def info(name: str = typer.Argument(help="Name of the dev environment", default=None)):
    """
    Show information about a dev env
    """
    container = None
    if name:
        try:
            container = docker.containers.get(name)
        except:
            typer.echo(f"Container '{name}' not found.")
    if not container:
        containers = docker.containers.list(filters={"label": "dev_env"})
        if not containers:
            typer.echo("No dev environments found.")
            return
        
        containerName = questionary.select(
            "Select a dev environment",
            choices=[c.name for c in containers]
        ).ask()
        if not containerName:
            typer.echo("No dev environment selected.")
            return
        container = docker.containers.get(containerName)


    typer.echo(f"ID: {container.id}")
    ports = container.attrs['NetworkSettings']['Ports']
    if ports:
        if '22/tcp' in ports:
            ssh_port = ports['22/tcp'][0]['HostPort']
            typer.echo(f"SSH Port: {ssh_port}")
        if '8080/tcp' in ports:
            vscode_port = ports['8080/tcp'][0]['HostPort']
            typer.echo(f"OpenVSCode Server Port: {vscode_port}")
        if '27017/tcp' in ports:
            mongodb_port = ports['27017/tcp'][0]['HostPort']
            typer.echo(f"MongoDB Port: {mongodb_port}")


@app.command(name="destroy")
def destroy(name: str = typer.Argument(help="Name of the dev environment", default=None)):
    """
    Destroy a dev env
    """
    container = None
    if name:
        try:
            container = docker.containers.get(name)
        except:
            typer.echo(f"Container '{name}' not found.")
    if not container:
        containers = docker.containers.list(filters={"label": "dev_env"})
        if not containers:
            typer.echo("No dev environments found.")
            return
        
        containerName = questionary.select(
            "Select a dev environment to destroy",
            choices=[c.name for c in containers]
        ).ask()
        if not containerName:
            typer.echo("No dev environment selected.")
            return
        container = docker.containers.get(containerName)

    confirm = questionary.confirm(f"Are you sure you want to destroy the dev environment '{container.name}'? This action cannot be undone.").ask()
    if not confirm:
        typer.echo("Aborting.")
        return

    with yaspin():
        container.remove(force=True)
    typer.echo(f"Dev environment '{container.name}' destroyed successfully.")


app()