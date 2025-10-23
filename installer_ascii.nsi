; Qingyuan Search Installer Script
; NSIS (Nullsoft Scriptable Install System) required

; Set Unicode support
Unicode True

!define APPNAME "QingYuan"
!define COMPANYNAME "QingYuan"
!define DESCRIPTION "Network Search Tool"
!define VERSIONMAJOR 1
!define VERSIONMINOR 2
!define VERSIONBUILD 0
!define HELPURL "https://github.com/your-repo/qingyuan"
!define UPDATEURL "https://github.com/your-repo/qingyuan"
!define ABOUTURL "https://github.com/your-repo/qingyuan"
!define INSTALLSIZE 50000
!define INSTALLERNAME "QingYuan_Setup.exe"

RequestExecutionLevel admin
InstallDir "$PROGRAMFILES\${APPNAME}"
Name "${APPNAME}"
outFile "${INSTALLERNAME}"

!include LogicLib.nsh

; Define variables
Var StartAfterInstall

page directory
page custom StartAfterInstallPage StartAfterInstallPageLeave
page instfiles

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin"
    messageBox mb_iconstop "Administrator privileges required to install ${APPNAME}."
    setErrorLevel 740
    quit
${EndIf}
!macroend

function .onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
    
    ; Check if old version is installed
    IfFileExists "$INSTDIR\QingYuan.exe" 0 +5
        MessageBox MB_OK "Detected installed QingYuan program.$\n$\nVersion Compatibility Notice:$\nNew version may not be fully compatible with old version configurations.$\nIf you encounter issues, please backup important configurations first."
    
    ; Default to start after install
    StrCpy $StartAfterInstall "1"
functionEnd

; Custom page: choose whether to start
Function StartAfterInstallPage
    nsDialogs::Create 1018
    Pop $0
    
    ${NSD_CreateLabel} 0 0 100% 20u "After installation, you can choose:"
    Pop $0
    
    ${NSD_CreateCheckbox} 10 30 100% 10u "Start QingYuan immediately"
    Pop $StartAfterInstall
    
    ; Default checked
    ${NSD_Check} $StartAfterInstall
    
    nsDialogs::Show
FunctionEnd

; Handle page leave
Function StartAfterInstallPageLeave
    ${NSD_GetState} $StartAfterInstall $StartAfterInstall
FunctionEnd

section "install"
    setOutPath $INSTDIR
    
    ; Backup existing config files if they exist
    IfFileExists "$INSTDIR\sites_config.json" 0 +3
        CopyFiles "$INSTDIR\sites_config.json" "$INSTDIR\sites_config.json.backup"
        MessageBox MB_OK "Backed up existing config file: sites_config.json"
    
    IfFileExists "$INSTDIR\proxy_config.json" 0 +3
        CopyFiles "$INSTDIR\proxy_config.json" "$INSTDIR\proxy_config.json.backup"
        MessageBox MB_OK "Backed up existing config file: proxy_config.json"
    
    ; Copy main program
    file "dist\*.exe"
    
    ; Copy config files (overwrite existing config)
    file "sites_config.json"
    file "proxy_config.json"
    
    ; Copy static files
    file /r "public"
    
    ; Copy documentation
    file "README.txt"
    
    ; Copy utility scripts
    file "close.bat"
    
    ; No shortcuts needed
    
    ; Write uninstaller
    writeUninstaller "$INSTDIR\uninstall.exe"
    
    ; Write registry information
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\QingYuan.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
sectionEnd

; Handle post-installation
Function .onInstSuccess
    ; Check if backup config files exist
    IfFileExists "$INSTDIR\sites_config.json.backup" 0 +8
        MessageBox MB_YESNO "Detected old version config files.$\n$\nVersion Compatibility Notice:$\nNew version config format may not be fully compatible with old version.$\n$\nDo you want to restore your custom configuration?$\n(Choose 'Yes' to restore your site config, 'No' to use default config)" IDYES RestoreConfig IDNO NoRestore
        RestoreConfig:
            CopyFiles "$INSTDIR\sites_config.json.backup" "$INSTDIR\sites_config.json"
            MessageBox MB_OK "Restored your site config file.$\n$\nIf the program starts abnormally, please check if the config format is correct."
        NoRestore:
    
    IfFileExists "$INSTDIR\proxy_config.json.backup" 0 +8
        MessageBox MB_YESNO "Detected old version proxy config files.$\n$\nVersion Compatibility Notice:$\nNew version proxy config format may not be fully compatible with old version.$\n$\nDo you want to restore your proxy configuration?" IDYES RestoreProxy IDNO NoRestoreProxy
        RestoreProxy:
            CopyFiles "$INSTDIR\proxy_config.json.backup" "$INSTDIR\proxy_config.json"
            MessageBox MB_OK "Restored your proxy config file.$\n$\nIf proxy function is abnormal, please check if the config format is correct."
        NoRestoreProxy:
    
    ; Check if start option is selected
    ${If} $StartAfterInstall == "1"
        MessageBox MB_OK "Installation completed! Starting QingYuan...$\n$\nAfter the program starts, please visit in your browser: http://127.0.0.1:8787"
        Exec "$INSTDIR\QingYuan.exe"
    ${Else}
        MessageBox MB_OK "Installation completed!$\n$\nYou can manually run $INSTDIR\QingYuan.exe to start the program."
    ${EndIf}
FunctionEnd

section "uninstall"
    ; Stop the program before uninstalling
    ExecWait '"$INSTDIR\close.bat"'
    
    ; Ask whether to keep config files
    MessageBox MB_YESNO "Do you want to keep your configuration files?$\n$\nChoose 'Yes' to keep the following files:$\n- sites_config.json (Site configuration)$\n- proxy_config.json (Proxy configuration)$\n$\nChoose 'No' to delete all files." IDYES KeepConfig IDNO DeleteAll
    
    KeepConfig:
        ; Keep config files, only delete program files
        delete "$INSTDIR\*.exe"
        delete "$INSTDIR\README.txt"
        delete "$INSTDIR\close.bat"
        delete "$INSTDIR\uninstall.exe"
        rmDir /r "$INSTDIR\public"
        ; Keep config files
        MessageBox MB_OK "Kept your configuration files.$\n$\nConfiguration files location: $INSTDIR"
        goto EndUninstall
    
    DeleteAll:
        ; Delete all files
        delete "$INSTDIR\*.exe"
        delete "$INSTDIR\sites_config.json"
        delete "$INSTDIR\proxy_config.json"
        delete "$INSTDIR\sites_config.json.backup"
        delete "$INSTDIR\proxy_config.json.backup"
        delete "$INSTDIR\README.txt"
        delete "$INSTDIR\close.bat"
        delete "$INSTDIR\uninstall.exe"
        rmDir /r "$INSTDIR\public"
        rmDir "$INSTDIR"
        goto EndUninstall
    
    EndUninstall:
        ; No shortcuts to delete
        
        ; Delete registry information
        DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
sectionEnd
