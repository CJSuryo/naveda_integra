# sync_landing.ps1 — regenerate landing/ from Django templates
# Run: .\sync_landing.ps1

$root = $PSScriptRoot

function Replace-Tags($src, $dst, $replacements) {
    $content = Get-Content $src -Raw -Encoding UTF8
    foreach ($pair in $replacements) {
        $content = $content -replace $pair[0], $pair[1]
    }
    $content | Set-Content $dst -Encoding UTF8
    Write-Host "  written: $dst"
}

# landing/index.html
Replace-Tags `
    "$root\templates\landing.html" `
    "$root\landing\index.html" `
    @(
        @("^\{%\s*load static\s*%\}\r?\n", ""),
        @("\{%\s*static 'css/landing\.css'\s*%\}", "css/landing.css"),
        @("\{%\s*url 'landing'\s*%\}", "./"),
        @("href=""\{%\s*if request\.user\.is_authenticated\s*%\}\{%\s*url 'home'\s*%\}\{%\s*else\s*%\}\{%\s*url 'login'\s*%\}\{%\s*endif\s*%\}""", 'href="https://naveda-integra.onrender.com/login/"'),
        @("\{%\s*if request\.user\.is_authenticated\s*%\}Masuk ke Sistem\{%\s*else\s*%\}Masuk\{%\s*endif\s*%\}", "Masuk"),
        @("\{%\s*url 'terms'\s*%\}", "terms.html"),
        @("\{%\s*static 'js/landing\.js'\s*%\}", "js/landing.js")
    )

# landing/terms.html
Replace-Tags `
    "$root\templates\legal\terms.html" `
    "$root\landing\terms.html" `
    @(
        @("^\{%\s*load static\s*%\}\r?\n", ""),
        @("\{%\s*static 'css/legal\.css'\s*%\}", "css/legal.css"),
        @("\{%\s*url 'landing'\s*%\}", "./"),
        @("\{%\s*static 'js/legal\.js'\s*%\}", "js/legal.js")
    )

# Copy assets
Copy-Item "$root\static\css\landing.css" "$root\landing\css\landing.css" -Force
Copy-Item "$root\static\css\legal.css"   "$root\landing\css\legal.css"   -Force
Copy-Item "$root\static\js\landing.js"   "$root\landing\js\landing.js"   -Force
Copy-Item "$root\static\js\legal.js"     "$root\landing\js\legal.js"     -Force
Copy-Item "$root\static\hero.png"        "$root\landing\hero.png"         -Force

Write-Host "Done. Commit landing/ to trigger Render deploy."
