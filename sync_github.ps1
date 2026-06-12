# ============================================================
# CelluleTrade Cash Bot - Synchronisation GitHub (push/pull)
# Double-clique sur sync_github.bat pour lancer ce script
# ============================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$repoUrl = "https://github.com/CelluleDev/CelluleTrade-Cash-Bot.git"

Write-Host "=== CelluleTrade Cash Bot - Synchronisation GitHub ===" -ForegroundColor Cyan
Write-Host ""

# 1. Initialiser le depot git si besoin
if (-not (Test-Path ".git")) {
    Write-Host "Initialisation du depot git local..." -ForegroundColor Cyan
    git init -b main
    git config user.name "Mickael"
    git config user.email "mikka66@live.fr"
}

# 2. Configurer le remote
$remotes = git remote
if ($remotes -notcontains "origin") {
    git remote add origin $repoUrl
} else {
    git remote set-url origin $repoUrl
}

# 3. Token GitHub optionnel (jamais enregistre sur le disque)
#    Si tu es deja connecte a GitHub via Git (Credential Manager), laisse vide :
#    une fenetre de connexion s'ouvrira automatiquement si besoin.
Write-Host ""
$tokenSecure = Read-Host "Colle ton token GitHub si tu en as un, sinon laisse vide" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($tokenSecure)
$token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

$gitArgs = @()
if ($token) {
    $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$token"))
    $gitArgs = @("-c", "http.extraheader=Authorization: Basic $basic")
}

# 4. Choix de l'action
Write-Host ""
Write-Host "1) Push (envoyer mes fichiers locaux vers GitHub)"
Write-Host "2) Pull (recuperer les changements depuis GitHub)"
$choice = Read-Host "Ton choix (1 ou 2)"

Write-Host ""
Write-Host "Connexion a GitHub..." -ForegroundColor Cyan
git @gitArgs fetch origin

$branch = git branch --show-current
if (-not $branch) { $branch = "main" }

if ($choice -eq "2") {
    git @gitArgs pull origin $branch --allow-unrelated-histories
    Write-Host ""
    Write-Host "Pull termine." -ForegroundColor Green
}
else {
    git add -A
    $status = git status --porcelain
    if ($status) {
        git commit -m "Mise a jour CelluleTrade Cash Bot ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))"
    } else {
        Write-Host "Rien de nouveau a committer." -ForegroundColor Yellow
    }

    $remoteBranch = git ls-remote --heads origin $branch
    if ($remoteBranch) {
        Write-Host "Fusion avec l'historique distant existant..." -ForegroundColor Cyan
        try {
            git merge -X ours --allow-unrelated-histories "origin/$branch" -m "Fusion avec historique distant"
        } catch {
            Write-Host "Fusion automatique impossible, conflits a resoudre manuellement." -ForegroundColor Red
            Write-Host $_
            Read-Host "Appuie sur Entree pour fermer"
            exit 1
        }
    }

    git @gitArgs push -u origin $branch
    Write-Host ""
    Write-Host "Push termine !" -ForegroundColor Green
}

Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
