"""Static guard for the standalone Windows dependency bootstrap contract."""
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]


class WindowsInstallerContractTests(unittest.TestCase):
    def test_winget_discovery_includes_app_installer_and_alias_repair(self):
        source=(SOURCE/'Install-TVPN-Windows.ps1').read_text(encoding='utf-8')
        self.assertIn("Get-AppxPackage -Name Microsoft.DesktopAppInstaller",source)
        self.assertIn("Microsoft\\WindowsApps\\winget.exe",source)
        self.assertIn("Add-AppxPackage -RegisterByFamilyName",source)

    def test_dependency_install_has_manual_fallback(self):
        source=(SOURCE/'Install-TVPN-Windows.ps1').read_text(encoding='utf-8')
        self.assertIn('Install Python 3.13 from python.org',source)
        self.assertIn('openvpn.net/community-downloads',source)
        self.assertIn('if (-not $winget)',source)


if __name__=='__main__':unittest.main()
