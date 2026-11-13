# Cria duas tarefas diarias no Agendador do Windows (07:10 e 19:10) que rodam scripts\rodar.bat
$bat = Join-Path $PSScriptRoot "rodar.bat"
schtasks /Create /F /TN "ava-sync manha" /TR "`"$bat`"" /SC DAILY /ST 07:10
schtasks /Create /F /TN "ava-sync noite" /TR "`"$bat`"" /SC DAILY /ST 19:10
Write-Host "Pronto. Para remover: schtasks /Delete /TN `"ava-sync manha`" /F  (idem `"ava-sync noite`")"
