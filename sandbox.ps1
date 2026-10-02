<#
Run Claude Code unattended in Docker on a separate clone of this repo.

  .\sandbox.ps1                    start the sandbox and open Claude Code (no permission prompts)
  .\sandbox.ps1 claude "prompt"    same, with a first prompt
  .\sandbox.ps1 shell              bash inside the agent container
  .\sandbox.ps1 check              prove the network limits hold (the gate in front of `claude`)
  .\sandbox.ps1 smoke              identity, unit tests, credentials, mounts (.sandbox\check.sh)
  .\sandbox.ps1 review             inspect the clone's git config and hooks, then fetch the agent's branch and list its commits
  .\sandbox.ps1 status             what is running
  .\sandbox.ps1 down               stop both containers (nothing is deleted)
  .\sandbox.ps1 recreate-agent     fresh agent container (the Claude login volume stays)
  .\sandbox.ps1 rebuild            rebuild both images after editing .sandbox\, then recreate the containers

Layout: the agent works in ..\nice_events_sandbox on branch "agent" and cannot push.
Its container sits on an --internal Docker network with no route out and reaches
the internet only through a Squid proxy that tunnels to the domains listed in
.sandbox\squid\squid.conf. This script and .sandbox\ live in this repo, not in the
clone the agent can write to: a script the agent could edit would run on the host.

Merging the agent's branch is deliberately not a command here. After `review`,
run the new test against the old code (it must fail there) before merging.
#>
param(
    [ValidateSet('claude', 'shell', 'check', 'smoke', 'review', 'status', 'down', 'recreate-agent', 'rebuild')]
    [string]$Command = 'claude',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$Repo = $PSScriptRoot
$Sandbox = Join-Path (Split-Path $Repo -Parent) 'nice_events_sandbox'
$Agent = 'nice-agent'
$Proxy = 'nice-sandbox-proxy'
$AgentImage = 'nice-events-agent'
$ProxyImage = 'nice-sandbox-proxy'
$NetInternal = 'nice-sandbox-internal'
$NetEgress = 'nice-sandbox-egress'
$ProxyUrl = "http://${Proxy}:3128"

function Assert-Ok([string]$What) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "$What failed (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

# --type container: the proxy's image has the same name as its container, and a bare
# `docker inspect` would find the image and report a removed container as existing.
function Test-Exists([string]$Name) {
    docker inspect --type container $Name 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-Running([string]$Name) {
    $state = docker inspect --type container -f '{{.State.Running}}' $Name 2>$null
    return ($LASTEXITCODE -eq 0 -and "$state".Trim() -eq 'true')
}

function Assert-Clone {
    if (-not (Test-Path (Join-Path $Sandbox '.git'))) {
        Write-Host "No sandbox clone at $Sandbox. Create it first:" -ForegroundColor Red
        Write-Host "  git clone --config core.autocrlf=false $Repo $Sandbox"
        Write-Host "  git -C $Sandbox switch -c agent"
        exit 1
    }
}

function Initialize-Networks {
    docker network inspect $NetInternal 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker network create --internal $NetInternal | Out-Null
        Assert-Ok 'create the internal network'
    }
    docker network inspect $NetEgress 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker network create $NetEgress | Out-Null
        Assert-Ok 'create the egress network'
    }
}

function Build-Proxy {
    docker build -t $ProxyImage -f (Join-Path $Repo '.sandbox\squid\Dockerfile') (Join-Path $Repo '.sandbox\squid')
    Assert-Ok 'build the proxy image'
}

function Build-Agent {
    docker build -t $AgentImage -f (Join-Path $Repo '.sandbox\Dockerfile') $Repo
    Assert-Ok 'build the agent image'
}

function Start-Proxy {
    docker image inspect $ProxyImage 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Build-Proxy }
    if (-not (Test-Exists $Proxy)) {
        # Created on the internal network first, then given the one network that has a way out.
        docker run -d --name $Proxy --network $NetInternal $ProxyImage | Out-Null
        Assert-Ok 'start the proxy'
        docker network connect $NetEgress $Proxy | Out-Null
        Assert-Ok 'connect the proxy to the egress network'
    } elseif (-not (Test-Running $Proxy)) {
        docker start $Proxy | Out-Null
        Assert-Ok 'start the proxy'
    }
}

function Start-Agent {
    docker image inspect $AgentImage 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Build-Agent }
    if (-not (Test-Exists $Agent)) {
        docker run -dit --name $Agent `
            --network $NetInternal `
            --cap-drop=ALL --security-opt=no-new-privileges `
            -v "${Sandbox}:/work" `
            -v nice-events-claude:/home/agent/.claude `
            -e "HTTP_PROXY=$ProxyUrl" -e "http_proxy=$ProxyUrl" `
            -e "HTTPS_PROXY=$ProxyUrl" -e "https_proxy=$ProxyUrl" `
            -e 'NO_PROXY=localhost,127.0.0.1' -e 'no_proxy=localhost,127.0.0.1' `
            $AgentImage | Out-Null
        Assert-Ok 'start the agent container'
    } elseif (-not (Test-Running $Agent)) {
        docker start $Agent | Out-Null
        Assert-Ok 'start the agent container'
    }
}

function Start-Sandbox {
    Assert-Clone
    Initialize-Networks
    Start-Proxy
    Start-Agent
}

# HTTP status code of a request made from inside the agent container; '000' means no connection.
function Get-ProbeCode([string[]]$CurlArgs) {
    $code = docker exec $Agent curl -s -o /dev/null -w '%{http_code}' --max-time 10 @CurlArgs 2>$null
    if (-not $code) { return '000' }
    return "$code".Trim()
}

# Prints PASS/FAIL per network limit; returns $true only if all hold.
function Test-NetworkLimits {
    if (-not ((Test-Running $Agent) -and (Test-Running $Proxy))) {
        Write-Host "The agent and the proxy must both be running: .\sandbox.ps1 status" -ForegroundColor Red
        return $false
    }
    $ok = $true

    $code = Get-ProbeCode @('https://api.anthropic.com/')
    if ($code -ne '000') { Write-Host "PASS  allowed domain reachable through the proxy ($code)" }
    else { Write-Host "FAIL  api.anthropic.com is not reachable through the proxy" -ForegroundColor Red; $ok = $false }

    $code = Get-ProbeCode @('https://example.com/')
    if ($code -eq '000') { Write-Host "PASS  other sites blocked by the proxy" }
    else { Write-Host "FAIL  example.com reachable through the proxy ($code)" -ForegroundColor Red; $ok = $false }

    $code = Get-ProbeCode @('--noproxy', '*', 'https://example.com/')
    if ($code -eq '000') { Write-Host "PASS  direct connection without the proxy is impossible" }
    else { Write-Host "FAIL  direct connection worked ($code)" -ForegroundColor Red; $ok = $false }

    if ($ok) { Write-Host "All limits hold." }
    else { Write-Host "A limit is broken. Do not run Claude Code with --dangerously-skip-permissions." -ForegroundColor Red }
    return $ok
}

# Reads the clone's git config and hooks as plain files (never through git: a hook or a config key
# like core.fsmonitor in a repo the agent can write would run on this machine), then fetches the branch.
function Show-AgentWork {
    Assert-Clone
    $gitDir = Join-Path $Sandbox '.git'
    $problems = @()

    $hooks = Get-ChildItem (Join-Path $gitDir 'hooks') -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '*.sample' }
    if ($hooks) { $problems += "hook files present: $(($hooks | ForEach-Object { $_.Name }) -join ', ')" }

    $config = Get-Content (Join-Path $gitDir 'config') -Raw
    $dangerous = '(?im)^\s*(fsmonitor|sshCommand|hooksPath|pager|editor|askPass|alias|textconv|program|helper|include|includeIf|insteadOf|clean|smudge|process)\b|^\s*\[(alias|include|includeIf|filter|credential|url|diff|merge|gpg)\b'
    foreach ($hit in [regex]::Matches($config, $dangerous)) { $problems += "config: $($hit.Value.Trim())" }
    $remotes = ([regex]::Matches($config, '(?m)^\s*\[remote\s')).Count
    if ($remotes -ne 1) { $problems += "config has $remotes remotes (expected exactly 1)" }

    if ($problems) {
        Write-Host "Not fetching: read these first, they would run on this machine." -ForegroundColor Red
        $problems | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Write-Host "Config file: $(Join-Path $gitDir 'config')"
        return
    }
    Write-Host "Clone config and hooks: nothing unusual."

    git -C $Repo fetch --quiet $Sandbox '+agent:refs/heads/agent-review'
    Assert-Ok 'git fetch the agent branch'
    $commits = git -C $Repo log --oneline master..agent-review
    if (-not $commits) {
        Write-Host "No new commits on the agent branch."
        return
    }
    Write-Host "Commits on the agent branch that master does not have:"
    $commits | ForEach-Object { Write-Host "  $_" }
    git -C $Repo --no-pager diff --stat master...agent-review | Out-Host
    Write-Host "Full diff:  git diff master...agent-review   (also read NOTES.md in it)"
    Write-Host "Before merging: run its new test on the old code (it must fail there), then ask Claude to merge."
    Write-Host "Afterwards drop the temporary branch:  git branch -D agent-review"
}

switch ($Command) {
    'claude' {
        Start-Sandbox
        if (-not (Test-NetworkLimits)) {
            Write-Host "Refusing to start the agent without its network limits." -ForegroundColor Red
            exit 1
        }
        docker exec -it -w /work $Agent claude --dangerously-skip-permissions @Rest
        exit $LASTEXITCODE
    }
    'shell' {
        Start-Sandbox
        docker exec -it -w /work $Agent bash -l
        exit $LASTEXITCODE
    }
    'check' {
        Start-Sandbox
        if (-not (Test-NetworkLimits)) { exit 1 }
    }
    'smoke' {
        Start-Sandbox
        # docker cp, not a PowerShell pipe: 5.1 would add a BOM and a trailing CR to the script text.
        docker cp (Join-Path $Repo '.sandbox\check.sh') "${Agent}:/tmp/check.sh"
        Assert-Ok 'copy check.sh into the container'
        docker exec -w /work $Agent bash /tmp/check.sh
    }
    'review' {
        Show-AgentWork
    }
    'status' {
        docker ps -a --filter "name=^($Agent|$Proxy)$" --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}'
    }
    'down' {
        docker stop $Agent $Proxy | Out-Null
        docker ps -a --filter "name=^($Agent|$Proxy)$" --format 'table {{.Names}}\t{{.Status}}'
    }
    'recreate-agent' {
        docker rm -f $Agent 2>$null | Out-Null
        Start-Sandbox
        docker ps -a --filter "name=^($Agent|$Proxy)$" --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}'
    }
    'rebuild' {
        Assert-Clone
        Build-Proxy
        Build-Agent
        docker rm -f $Agent $Proxy 2>$null | Out-Null
        Start-Sandbox
        docker ps -a --filter "name=^($Agent|$Proxy)$" --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}'
    }
}
exit 0   # not the exit code the last probe inside the container happened to leave behind
