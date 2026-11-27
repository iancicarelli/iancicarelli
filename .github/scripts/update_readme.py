"""Actualiza README.md con datos de los repositorios públicos (sin forks)."""
import json, os, re, subprocess, tempfile, urllib.request
from collections import Counter
from pathlib import Path

USER = os.environ.get("GH_USER", "iancicarelli")
TOKEN = os.environ.get("GITHUB_TOKEN")

# nombre visible -> dependencia que lo delata
TECH = {
    "Vue": "vue", "Nuxt": "nuxt", "React": "react", "NestJS": "@nestjs/core",
    "Tailwind CSS": "tailwindcss", "Phaser": "phaser", "TypeORM": "typeorm", "Jest": "jest",
    "FastAPI": "fastapi", "SQLAlchemy": "sqlalchemy", "Reflex": "reflex",
    "Spring Boot": "spring-boot", "Axum": "axum", "Leptos": "leptos", "SeaORM": "sea-orm",
    "Flutter": "flutter", "PostgreSQL": "postgres", "MySQL": "mysql",
}
SKIP = {"node_modules", ".git", "target", "build", "dist", "venv", ".venv"}


def api(path):
    req = urllib.request.Request("https://api.github.com" + path)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def dependencies(file):
    """Nombres de dependencias declaradas en un archivo de proyecto."""
    name = file.name
    text = file.read_text(errors="ignore").lower()
    if name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return set()
        return {*data.get("dependencies", {}), *data.get("devdependencies", {})}
    if name == "requirements.txt":
        return {m.group(0) for line in text.splitlines() if (m := re.match(r"[a-z0-9_.-]+", line.strip()))}
    found = set()
    if name in ("Cargo.toml", "pubspec.yaml"):
        found |= set(re.findall(r"^\s*([a-z0-9_-]+)\s*[=:.]", text, re.M))
    if name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        found |= {k for k in ("spring-boot", "mysql", "postgres") if k in text}
    if name.startswith("docker-compose") or name.startswith("compose."):
        found |= {m for m in re.findall(r"image:\s*['\"]?(postgres|mysql)", text)}
    return found


def detect(folder):
    deps, docker = set(), False
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f == "Dockerfile" or f.startswith("docker-compose"):
                docker = True
            if f in ("package.json", "requirements.txt", "Cargo.toml", "pubspec.yaml", "pom.xml",
                     "build.gradle", "build.gradle.kts") or f.startswith("docker-compose"):
                deps |= dependencies(Path(root, f))
    techs = {label for label, dep in TECH.items() if dep in deps}
    return techs | ({"Docker"} if docker else set())


def replace(readme, tag, body):
    pattern = rf"(<!-- {tag}:START -->).*?(<!-- {tag}:END -->)"
    new, n = re.subn(pattern, lambda m: f"{m[1]}\n{body}\n{m[2]}", readme, flags=re.S)
    if not n:
        raise SystemExit(f"Faltan los marcadores {tag} en README.md")
    return new


def main():
    repos, page = [], 1
    while batch := api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner"):
        repos += batch
        page += 1
    repos = [r for r in repos if not r["fork"] and not r["private"] and r["name"].lower() != USER.lower()]

    langs, techs = Counter(), Counter()
    with tempfile.TemporaryDirectory() as tmp:
        for r in repos:
            langs.update(api(f"/repos/{USER}/{r['name']}/languages"))
            dest = os.path.join(tmp, r["name"])
            subprocess.run(["git", "clone", "-q", "--depth", "1", r["clone_url"], dest],
                           check=True, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
            techs.update(detect(dest))

    stack = " ".join(f"`{t}`" for t, _ in sorted(techs.items(), key=lambda x: (-x[1], x[0])))
    total = sum(langs.values()) or 1
    bars = "\n".join(
        f"{name:<14} {'█' * round(size / total * 25):<25} {size / total:6.1%}"
        for name, size in langs.most_common(6))
    stars = sum(r["stargazers_count"] for r in repos)
    stats = (f"**{len(repos)}** public repositories · **{stars}** stars · "
             f"**{api(f'/users/{USER}')['followers']}** followers\n\n```text\n{bars}\n```")

    path = Path("README.md")
    text = replace(path.read_text(encoding="utf-8"), "STACK", stack)
    path.write_text(replace(text, "STATS", stats), encoding="utf-8")


if __name__ == "__main__":
    main()
