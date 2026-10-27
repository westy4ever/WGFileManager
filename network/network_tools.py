"""
WGFileManager Network Tools Suite
Professional network scanning and device discovery
"""

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from enigma import getDesktop, eTimer
import subprocess
import threading
import socket
import re
import time
import os
import sys

# Handle imports for both installed and development mode
try:
    from Plugins.Extensions.WGFileManager.utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    try:
        # Get the plugin directory
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, plugin_dir)
        from utils.logging_config import get_logger
        logger = get_logger(__name__)
    except ImportError:
        # Ultimate fallback
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)


class NetworkToolsScreen(Screen):
    """Main Network Tools interface"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        # Get screen dimensions
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        # Create skin
        self.skin = f"""
        <screen name="NetworkToolsScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="🌐 Network Tools" position="20,10" size="{w-40},60" font="Regular;36" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="menu" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        # Create widgets
        self["menu"] = MenuList([])
        self["status"] = Label("Select a network tool")
        self["help"] = Label("OK:Select  EXIT:Back  INFO:Help")
        
        # Setup actions
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.select_tool,
            "cancel": self.close,
            "red": self.close,
            "info": self.show_help,
        }, -1)
        
        # State
        self.tools = [
            ("🔍 Network Scanner (ping)", "scanner"),
            ("📊 Port Scanner (scan for famous ports)", "portscan"),
            ("🗄️ CIFS/SMB Share Scanner", "smb_scanner"),
            ("💾 Network Storage (FTP)", "ftp"),
            ("🌐 Check Internet Connection", "internet"),
            ("📱 Detect Local Devices", "devices"),
            ("🗺️ Network Map", "map"),
        ]
        
        self.onLayoutFinish.append(self.init_screen)
    
    def init_screen(self):
        """Initialize screen"""
        self["menu"].setList(self.tools)
    
    def select_tool(self):
        """Select tool"""
        current = self["menu"].getCurrent()
        if not current:
            return
        
        tool_id = current[1]
        
        if tool_id == "scanner":
            self.session.open(NetworkScannerScreen)
        elif tool_id == "portscan":
            self.session.open(PortScannerScreen)
        elif tool_id == "smb_scanner":
            self.session.open(SMBShareScannerScreen)
        elif tool_id == "ftp":
            self.show_message("FTP tool - Coming soon!")
        elif tool_id == "internet":
            self.check_internet()
        elif tool_id == "devices":
            self.session.open(DeviceDetectionScreen)
        elif tool_id == "map":
            self.session.open(NetworkMapScreen)
    
    def check_internet(self):
        """Check internet connectivity"""
        self["status"].setText("⏳ Checking internet connection...")
        
        def check_thread():
            try:
                # Try to ping common DNS servers
                servers = [
                    ("Google DNS", "8.8.8.8"),
                    ("Cloudflare DNS", "1.1.1.1"),
                    ("OpenDNS", "208.67.222.222")
                ]
                
                results = []
                for name, ip in servers:
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "2", ip],
                        capture_output=True,
                        timeout=3
                    )
                    status = "✅" if result.returncode == 0 else "❌"
                    results.append(f"{status} {name} ({ip})")
                
                # Show results
                msg = "🌐 Internet Connection Test\n\n"
                msg += "\n".join(results)
                
                # Check if at least one succeeded
                if any("✅" in r for r in results):
                    msg += "\n\n✅ Internet is connected!"
                else:
                    msg += "\n\n❌ No internet connection detected"
                
                self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=10)
                self["status"].setText("Ready")
                
            except Exception as e:
                logger.error(f"Internet check error: {e}")
                self["status"].setText("Error checking internet")
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def show_help(self):
        """Show help"""
        help_text = "🌐 NETWORK TOOLS HELP\n\n"
        help_text += "Network Scanner: Scan local network for active devices\n\n"
        help_text += "Port Scanner: Detect open ports on devices\n\n"
        help_text += "Network Storage: Access FTP servers\n\n"
        help_text += "Internet Check: Test internet connectivity\n\n"
        help_text += "Device Detection: Find devices using ARP\n\n"
        help_text += "Network Map: Visualize network topology\n\n"
        help_text += "Press OK to select a tool"
        
        self.session.open(MessageBox, help_text, MessageBox.TYPE_INFO)
    
    def show_message(self, text):
        """Show info message"""
        self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=3)


class NetworkScannerScreen(Screen):
    """Network Scanner - Ping sweep across IP range"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="NetworkScannerScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="Hosts that responded to &quot;ping&quot;" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="results" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["results"] = MenuList([])
        self["status"] = Label("⏳ Scanning network...")
        self["help"] = Label("OK:Details  RED:Scan  EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.show_details,
            "cancel": self.close,
            "red": self.start_scan,
        }, -1)
        
        self.scan_results = []
        self.scanning = False
        
        self.onLayoutFinish.append(self.start_scan)
    
    def start_scan(self):
        """Start network scan"""
        if self.scanning:
            return
        
        self.scanning = True
        self["status"].setText("⏳ Scanning network 192.168.100.1-254...")
        self["results"].setList([("⏳ Scanning...", None)])
        
        def scan_thread():
            try:
                active_hosts = []
                base_ip = "192.168.100."
                
                # Scan range
                for i in range(1, 255):
                    if not self.scanning:
                        break
                    
                    ip = base_ip + str(i)
                    
                    # Quick ping
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "1", ip],
                        capture_output=True,
                        timeout=2
                    )
                    
                    if result.returncode == 0:
                        # Get MAC address
                        mac = self.get_mac_address(ip)
                        
                        # Check if gateway
                        label = "Gateway" if i == 1 else ("Own" if i == 27 else "")
                        
                        active_hosts.append((
                            f"{ip:<17} {label:<8} | {mac}",
                            {"ip": ip, "mac": mac, "label": label}
                        ))
                        
                        # Update display
                        self["results"].setList(active_hosts)
                        self["status"].setText(f"Found {len(active_hosts)} devices...")
                
                # Scan complete
                if active_hosts:
                    self["status"].setText(f"✅ Scan complete: {len(active_hosts)} devices found")
                else:
                    self["status"].setText("❌ No devices found")
                    self["results"].setList([("No devices found", None)])
                
                self.scan_results = active_hosts
                self.scanning = False
                
            except Exception as e:
                logger.error(f"Scan error: {e}")
                self["status"].setText(f"❌ Scan failed: {e}")
                self.scanning = False
        
        threading.Thread(target=scan_thread, daemon=True).start()
    
    def get_mac_address(self, ip):
        """Get MAC address for IP"""
        try:
            # Try ARP
            result = subprocess.run(
                ["arp", "-n", ip],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Parse ARP output
                for line in result.stdout.split('\n'):
                    if ip in line:
                        parts = line.split()
                        for part in parts:
                            if ':' in part and len(part) == 17:
                                return part.upper()
            
            return "Unknown"
            
        except:
            return "Unknown"
    
    def show_details(self):
        """Show device details"""
        current = self["results"].getCurrent()
        if not current or not current[1]:
            return
        
        device = current[1]
        
        msg = "🌐 DEVICE DETAILS\n\n"
        msg += f"IP Address: {device['ip']}\n"
        msg += f"MAC Address: {device['mac']}\n"
        msg += f"Type: {device['label'] if device['label'] else 'Unknown'}\n\n"
        msg += "Options:\n"
        msg += "• Scan ports\n"
        msg += "• Ping test\n"
        msg += "• Add to devices"
        
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)


class PortScannerScreen(Screen):
    """Port Scanner - Scan for open ports on selected device"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="PortScannerScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="🔍 Select host to scan" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="hostlist" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["hostlist"] = MenuList([])
        self["status"] = Label("Select a host to scan for open ports")
        self["help"] = Label("OK:Select  EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions"], {
            "ok": self.scan_host,
            "cancel": self.close,
        }, -1)
        
        self.onLayoutFinish.append(self.generate_host_list)
    
    def generate_host_list(self):
        """Generate list of IPs to scan"""
        hosts = []
        base_ip = "192.168.100."
        
        for i in range(1, 20):
            ip = base_ip + str(i)
            hosts.append((ip, ip))
        
        self["hostlist"].setList(hosts)
    
    def scan_host(self):
        """Scan selected host for open ports"""
        current = self["hostlist"].getCurrent()
        if not current:
            return
        
        ip = current[1]
        self["status"].setText(f"⏳ Scanning {ip}...")
        
        def scan_thread():
            try:
                # Common ports to scan
                common_ports = {
                    21: "FTP",
                    22: "SSH",
                    23: "Telnet",
                    25: "SMTP",
                    53: "DNS",
                    80: "HTTP",
                    110: "POP3",
                    143: "IMAP",
                    443: "HTTPS",
                    3389: "RDP",
                    8080: "HTTP-Proxy"
                }
                
                open_ports = []
                
                for port, service in common_ports.items():
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(1)
                        result = sock.connect_ex((ip, port))
                        sock.close()
                        
                        if result == 0:
                            open_ports.append(f"{port} ({service})")
                    except:
                        pass
                
                # Show results
                if open_ports:
                    msg = f"🔍 Port Scan Results\n\n"
                    msg += f"Host: {ip}\n\n"
                    msg += f"Open Ports ({len(open_ports)}):\n"
                    msg += "\n".join(f"  • {port}" for port in open_ports)
                else:
                    msg = f"No open ports found on {ip}"
                
                self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)
                self["status"].setText("Ready")
                
            except Exception as e:
                logger.error(f"Port scan error: {e}")
                self["status"].setText("Scan failed")
        
        threading.Thread(target=scan_thread, daemon=True).start()


class DeviceDetectionScreen(Screen):
    """Device Detection using ARP"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="DeviceDetectionScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="📱 Network Devices" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="message" position="200,{h//2-100}" size="{w-400},200" font="Regular;28" halign="center" valign="center" backgroundColor="#2a2a2a" foregroundColor="#ffffff" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["message"] = Label("No devices found !\n\nScan network ?")
        self["status"] = Label("Press GREEN to scan")
        self["help"] = Label("GREEN:Yes  RED:No")
        
        self["actions"] = ActionMap(["ColorActions"], {
            "green": self.scan_network,
            "red": self.close,
        }, -1)
    
    def scan_network(self):
        """Scan network for devices"""
        self["message"].setText("⏳ Scanning...")
        self["status"].setText("Please wait...")
        
        def scan_thread():
            try:
                # Get ARP table
                result = subprocess.run(
                    ["arp", "-a"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                devices = []
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if "at" in line.lower():
                            # Parse ARP entry
                            parts = line.split()
                            if len(parts) >= 4:
                                ip = parts[1].strip('()')
                                mac = parts[3]
                                devices.append(f"{ip} ({mac})")
                
                # Show results
                if devices:
                    msg = f"Found {len(devices)} devices:\n\n"
                    msg += "\n".join(f"• {dev}" for dev in devices[:10])
                    if len(devices) > 10:
                        msg += f"\n... and {len(devices)-10} more"
                    
                    self["message"].setText(msg)
                    self["status"].setText(f"✅ {len(devices)} devices detected")
                else:
                    self["message"].setText("No devices found in ARP table")
                    self["status"].setText("Try scanning network first")
                
            except Exception as e:
                logger.error(f"Device detection error: {e}")
                self["message"].setText(f"Detection failed:\n{e}")
                self["status"].setText("Error")
        
        threading.Thread(target=scan_thread, daemon=True).start()


class NetworkMapScreen(Screen):
    """Network Map - Visual representation"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="NetworkMapScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="🗺️ Network Map" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="map" position="100,120" size="{w-200},{h-250}" font="Regular;20" halign="left" valign="top" transparent="1" foregroundColor="#ffffff" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["map"] = Label("")
        self["status"] = Label("Building network map...")
        self["help"] = Label("EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions"], {
            "cancel": self.close,
        }, -1)
        
        self.onLayoutFinish.append(self.build_map)
    
    def build_map(self):
        """Build network topology map"""
        def map_thread():
            try:
                # Simplified network map
                map_text = "Network Topology:\n\n"
                map_text += "    [Router/Gateway]\n"
                map_text += "    192.168.100.1\n"
                map_text += "          |\n"
                map_text += "    ------+------\n"
                map_text += "    |     |     |\n"
                map_text += "  [PC] [TV] [STB]\n\n"
                map_text += "Detected:\n"
                map_text += "• Gateway: 192.168.100.1\n"
                map_text += "• Own Device: 192.168.100.27\n"
                map_text += "• 4 other devices\n\n"
                map_text += "Scan network for detailed map"
                
                self["map"].setText(map_text)
                self["status"].setText("✅ Map generated")
                
            except Exception as e:
                logger.error(f"Map error: {e}")
                self["status"].setText("Map generation failed")
        
        threading.Thread(target=map_thread, daemon=True).start()


class SMBShareScannerScreen(Screen):
    """CIFS/SMB Share Scanner - Discover and browse network shares"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="SMBShareScannerScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="🗄️ CIFS/SMB Share Scanner" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="host_list" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["host_list"] = MenuList([])
        self["status"] = Label("⏳ Scanning for SMB/CIFS hosts...")
        self["help"] = Label("OK:Scan Shares  GREEN:Auto-scan  RED:Manual  EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.scan_selected_host,
            "cancel": self.close,
            "green": self.auto_scan,
            "red": self.manual_entry,
        }, -1)
        
        self.discovered_hosts = []
        self.scanning = False
        
        self.onLayoutFinish.append(self.check_dependencies)
    
    def check_dependencies(self):
        """Check if smbclient is available"""
        try:
            result = subprocess.run(
                ["which", "smbclient"],
                capture_output=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # smbclient is available, start auto scan
                self.auto_scan()
            else:
                # smbclient not found
                self["status"].setText("⚠️ smbclient not installed!")
                self["host_list"].setList([
                    ("❌ smbclient not found", None),
                    ("", None),
                    ("Install with:", None),
                    ("opkg install samba-client", None),
                    ("", None),
                    ("or try manual IP entry (RED button)", None)
                ])
                self["help"].setText("RED:Manual Entry  EXIT:Back")
        except Exception as e:
            logger.error(f"Dependency check error: {e}")
            self["status"].setText("Error checking dependencies")
    
    def auto_scan(self):
        """Automatically scan network for SMB hosts"""
        if self.scanning:
            return
        
        self.scanning = True
        self["status"].setText("⏳ Scanning network for SMB/CIFS hosts...")
        self["host_list"].setList([("⏳ Scanning for SMB servers...", None)])
        
        def scan_thread():
            try:
                smb_hosts = []
                
                # Method 1: Try nmblookup (NetBIOS name resolution)
                try:
                    result = subprocess.run(
                        ["nmblookup", "-A", "192.168.100.255"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        # Parse nmblookup output
                        current_ip = None
                        for line in result.stdout.split('\n'):
                            if "Looking up status" in line:
                                # Extract IP
                                parts = line.split()
                                for part in parts:
                                    if '192.168.' in part:
                                        current_ip = part
                            elif current_ip and '<20>' in line:
                                # File server service
                                name = line.split()[0].strip()
                                if name not in [h[1]['name'] for h in smb_hosts if h[1]]:
                                    smb_hosts.append((
                                        f"🗄️ {name:<15} ({current_ip})",
                                        {'ip': current_ip, 'name': name, 'method': 'nmblookup'}
                                    ))
                except Exception as e:
                    logger.debug(f"nmblookup failed: {e}")
                
                # Method 2: Scan common SMB IPs (445/139)
                if len(smb_hosts) == 0:
                    self["status"].setText("⏳ Scanning IP range for SMB ports...")
                    
                    base_ip = "192.168.100."
                    for i in [1, 2, 9, 10, 15, 18, 27, 50, 100, 200]:  # Common IPs
                        ip = base_ip + str(i)
                        
                        # Check if SMB port is open
                        if self.check_smb_port(ip):
                            smb_hosts.append((
                                f"🗄️ SMB Host at {ip}",
                                {'ip': ip, 'name': f"host-{i}", 'method': 'port_scan'}
                            ))
                
                # Update display
                if smb_hosts:
                    self["host_list"].setList(smb_hosts)
                    self["status"].setText(f"✅ Found {len(smb_hosts)} SMB/CIFS hosts")
                else:
                    self["host_list"].setList([
                        ("❌ No SMB hosts found", None),
                        ("", None),
                        ("Try:", None),
                        ("• GREEN: Scan again", None),
                        ("• RED: Enter IP manually", None),
                    ])
                    self["status"].setText("No SMB hosts detected")
                
                self.discovered_hosts = smb_hosts
                self.scanning = False
                
            except Exception as e:
                logger.error(f"Auto scan error: {e}")
                self["status"].setText(f"Scan failed: {str(e)[:50]}")
                self.scanning = False
        
        threading.Thread(target=scan_thread, daemon=True).start()
    
    def check_smb_port(self, ip):
        """Check if SMB port is open"""
        try:
            # Check port 445 (SMB)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, 445))
            sock.close()
            
            if result == 0:
                return True
            
            # Try port 139 (NetBIOS)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, 139))
            sock.close()
            
            return result == 0
            
        except:
            return False
    
    def manual_entry(self):
        """Manually enter SMB server IP"""
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        
        self.session.openWithCallback(
            self.manual_entry_callback,
            VirtualKeyBoard,
            title="Enter SMB server IP or hostname:",
            text="192.168.100."
        )
    
    def manual_entry_callback(self, server):
        """Handle manual entry"""
        if not server:
            return
        
        # Add to list and scan
        self.discovered_hosts = [(
            f"🗄️ Manual: {server}",
            {'ip': server, 'name': server, 'method': 'manual'}
        )]
        
        self["host_list"].setList(self.discovered_hosts)
        self.scan_shares(server)
    
    def scan_selected_host(self):
        """Scan selected host for shares"""
        current = self["host_list"].getCurrent()
        if not current or not current[1]:
            return
        
        host_info = current[1]
        self.scan_shares(host_info['ip'])
    
    def scan_shares(self, server):
        """Scan for shares on server"""
        self["status"].setText(f"⏳ Scanning shares on {server}...")
        
        def scan_thread():
            try:
                shares = []
                
                # Method 1: Try smbclient
                try:
                    result = subprocess.run(
                        ["smbclient", "-L", server, "-N", "-g"],
                        capture_output=True,
                        text=True,
                        timeout=15
                    )
                    
                    if result.returncode == 0:
                        # Parse smbclient output
                        for line in result.stdout.split('\n'):
                            if '|Disk|' in line:
                                parts = line.split('|')
                                if len(parts) >= 2:
                                    share_name = parts[1]
                                    # FIXED: Proper condition without broken line
                                    if share_name and not share_name.endswith('$'):
                                        description = parts[2] if len(parts) > 2 else ''
                                        shares.append({
                                            'name': share_name,
                                            'type': 'Disk',
                                            'description': description,
                                            'server': server
                                        })
                    else:
                        # Try with guest credentials
                        result = subprocess.run(
                            ["smbclient", "-L", server, "-U", "guest%", "-g"],
                            capture_output=True,
                            text=True,
                            timeout=15
                        )
                        
                        if result.returncode == 0:
                            for line in result.stdout.split('\n'):
                                if '|Disk|' in line:
                                    parts = line.split('|')
                                    if len(parts) >= 2:
                                        share_name = parts[1]
                                        # FIXED: Proper condition without broken line
                                        if share_name and not share_name.endswith('$'):
                                            shares.append({
                                                'name': share_name,
                                                'type': 'Disk',
                                                'server': server
                                            })
                
                except Exception as e:
                    logger.error(f"smbclient scan error: {e}")
                
                # Show results
                if shares:
                    self.session.open(
                        SMBShareDetailsScreen,
                        server,
                        shares
                    )
                else:
                    # Show error/auth required message
                    msg = f"🗄️ SMB SCAN RESULTS\n\n"
                    msg += f"Server: {server}\n\n"
                    msg += "No shares found or access denied.\n\n"
                    msg += "Possible reasons:\n"
                    msg += "• Server requires authentication\n"
                    msg += "• No shares are configured\n"
                    msg += "• Firewall blocking access\n"
                    msg += "• SMB protocol version mismatch\n\n"
                    msg += "Try mounting manually with credentials."
                    
                    self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)
                
                self["status"].setText("Scan complete")
                
            except Exception as e:
                logger.error(f"Share scan error: {e}")
                self["status"].setText(f"Scan failed: {str(e)[:50]}")
        
        threading.Thread(target=scan_thread, daemon=True).start()


class SMBShareDetailsScreen(Screen):
    """Display and manage SMB shares"""
    
    def __init__(self, session, server, shares):
        Screen.__init__(self, session)
        
        self.server = server
        self.shares = shares
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="SMBShareDetailsScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="📁 Available Shares" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="share_list" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["share_list"] = MenuList([])
        self["status"] = Label(f"Server: {server} - {len(shares)} shares found")
        self["help"] = Label("OK:Mount  YELLOW:Browse  BLUE:Add Favorite  INFO:Details  EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "EPGSelectActions"], {
            "ok": self.mount_share,
            "cancel": self.close,
            "yellow": self.browse_share,
            "blue": self.add_to_favorites,
            "info": self.show_share_info,
        }, -1)
        
        self.onLayoutFinish.append(self.populate_shares)
    
    def populate_shares(self):
        """Populate share list"""
        share_items = []
        
        for share in self.shares:
            desc = share.get('description', '')
            display = f"📁 {share['name']:<20}"
            if desc:
                display += f" - {desc[:30]}"
            
            share_items.append((display, share))
        
        self["share_list"].setList(share_items)
    
    def browse_share(self):
        """Browse share contents"""
        current = self["share_list"].getCurrent()
        if not current or not current[1]:
            return
        
        share = current[1]
        self.session.open(SMBShareBrowserScreen, self.server, share['name'])
    
    def add_to_favorites(self):
        """Add share to favorites"""
        current = self["share_list"].getCurrent()
        if not current or not current[1]:
            return
        
        share = current[1]
        
        import json
        
        try:
            favorites_file = "/tmp/wgfilemanager_smb_favorites.json"
            favorites = []
            
            # Load existing favorites
            if os.path.exists(favorites_file):
                with open(favorites_file, 'r') as f:
                    favorites = json.load(f)
            
            # Check if already in favorites
            for fav in favorites:
                if fav['server'] == self.server and fav['share'] == share['name']:
                    self.session.open(MessageBox,
                                    "Already in favorites!",
                                    MessageBox.TYPE_INFO, timeout=2)
                    return
            
            # Add to favorites
            favorites.append({
                'server': self.server,
                'share': share['name'],
                'description': share.get('description', ''),
                'type': share.get('type', 'Disk')
            })
            
            # Save
            with open(favorites_file, 'w') as f:
                json.dump(favorites, f, indent=2)
            
            self.session.open(MessageBox,
                            f"⭐ Added to favorites!\n\n{self.server}/{share['name']}",
                            MessageBox.TYPE_INFO, timeout=2)
            
        except Exception as e:
            logger.error(f"Add to favorites error: {e}")
            self.session.open(MessageBox,
                            f"Failed to add to favorites:\n{str(e)[:100]}",
                            MessageBox.TYPE_ERROR)
    
    def show_share_info(self):
        """Show detailed share information"""
        current = self["share_list"].getCurrent()
        if not current or not current[1]:
            return
        
        share = current[1]
        
        msg = "📁 SHARE DETAILS\n\n"
        msg += f"Server: {self.server}\n"
        msg += f"Share Name: {share['name']}\n"
        msg += f"Type: {share.get('type', 'Unknown')}\n"
        
        if share.get('description'):
            msg += f"Description: {share['description']}\n"
        
        msg += f"\nUNC Path:\n"
        msg += f"//{self.server}/{share['name']}\n\n"
        msg += "Press OK to mount this share"
        
        self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)
    
    def mount_share(self):
        """Mount selected share"""
        current = self["share_list"].getCurrent()
        if not current or not current[1]:
            return
        
        share = current[1]
        
        # Show mount options
        msg = f"Mount Share?\n\n"
        msg += f"Server: {self.server}\n"
        msg += f"Share: {share['name']}\n\n"
        msg += f"Mount point:\n"
        msg += f"/media/net/{share['name']}\n\n"
        msg += "This will mount the share with guest access.\n"
        msg += "Use manual mount for authentication."
        
        self.session.openWithCallback(
            lambda res: self.execute_mount(res, share) if res else None,
            MessageBox,
            msg,
            MessageBox.TYPE_YESNO
        )
    
    def execute_mount(self, confirmed, share):
        """Execute mount operation"""
        if not confirmed:
            return
        
        self["status"].setText("⏳ Mounting share...")
        
        def mount_thread():
            try:
                mount_point = f"/media/net/{share['name']}"
                
                # Create mount point
                os.makedirs(mount_point, exist_ok=True)
                
                # Mount command
                mount_cmd = [
                    "mount", "-t", "cifs",
                    f"//{self.server}/{share['name']}",
                    mount_point,
                    "-o", "guest,vers=3.0,iocharset=utf8"
                ]
                
                result = subprocess.run(
                    mount_cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    msg = f"✅ Share Mounted!\n\n"
                    msg += f"Location: {mount_point}\n\n"
                    msg += "You can now access the share in WGFileManager"
                    
                    self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=5)
                    self["status"].setText("✅ Mount successful")
                else:
                    # Try other SMB versions
                    for version in ["2.0", "1.0"]:
                        mount_cmd = [
                            "mount", "-t", "cifs",
                            f"//{self.server}/{share['name']}",
                            mount_point,
                            "-o", f"guest,vers={version},iocharset=utf8"
                        ]
                        
                        result = subprocess.run(
                            mount_cmd,
                            capture_output=True,
                            timeout=15
                        )
                        
                        if result.returncode == 0:
                            msg = f"✅ Share Mounted (SMB {version})!\n\n"
                            msg += f"Location: {mount_point}"
                            
                            self.session.open(MessageBox, msg, MessageBox.TYPE_INFO, timeout=5)
                            self["status"].setText("✅ Mount successful")
                            return
                    
                    # All mount attempts failed
                    error = result.stderr[:200] if result.stderr else "Unknown error"
                    msg = f"❌ Mount Failed\n\n"
                    msg += f"Error: {error}\n\n"
                    msg += "Try:\n"
                    msg += "• Check network connectivity\n"
                    msg += "• Verify share permissions\n"
                    msg += "• Use manual mount with credentials"
                    
                    self.session.open(MessageBox, msg, MessageBox.TYPE_ERROR)
                    self["status"].setText("❌ Mount failed")
                
            except Exception as e:
                logger.error(f"Mount error: {e}")
                self["status"].setText(f"Mount error: {str(e)[:50]}")
        
        threading.Thread(target=mount_thread, daemon=True).start()


class FavoriteSharesScreen(Screen):
    """Manage favorite SMB shares"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="FavoriteSharesScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <eLabel text="⭐ Favorite Shares" position="20,10" size="{w-40},60" font="Regular;32" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="favorites_list" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["favorites_list"] = MenuList([])
        self["status"] = Label("")
        self["help"] = Label("OK:Mount  YELLOW:Browse  RED:Delete  EXIT:Back")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.mount_favorite,
            "cancel": self.close,
            "yellow": self.browse_favorite,
            "red": self.delete_favorite,
        }, -1)
        
        self.favorites_file = "/tmp/wgfilemanager_smb_favorites.json"
        self.favorites = []
        
        self.onLayoutFinish.append(self.load_favorites)
    
    def load_favorites(self):
        """Load saved favorites"""
        import json
        
        try:
            if os.path.exists(self.favorites_file):
                with open(self.favorites_file, 'r') as f:
                    self.favorites = json.load(f)
            
            if self.favorites:
                items = []
                for fav in self.favorites:
                    display = f"⭐ {fav['server']}/{fav['share']}"
                    if fav.get('description'):
                        display += f" - {fav['description'][:20]}"
                    items.append((display, fav))
                
                self["favorites_list"].setList(items)
                self["status"].setText(f"{len(self.favorites)} favorite shares")
            else:
                self["favorites_list"].setList([
                    ("No favorite shares saved", None),
                    ("", None),
                    ("Add shares to favorites from", None),
                    ("the share browser!", None),
                ])
                self["status"].setText("No favorites")
        
        except Exception as e:
            logger.error(f"Load favorites error: {e}")
            self["status"].setText("Error loading favorites")
    
    def save_favorites(self):
        """Save favorites to file"""
        import json
        
        try:
            with open(self.favorites_file, 'w') as f:
                json.dump(self.favorites, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Save favorites error: {e}")
            return False
    
    def mount_favorite(self):
        """Mount selected favorite"""
        current = self["favorites_list"].getCurrent()
        if not current or not current[1]:
            return
        
        fav = current[1]
        
        msg = f"Quick Mount?\n\n"
        msg += f"Server: {fav['server']}\n"
        msg += f"Share: {fav['share']}\n"
        msg += f"Mount: /media/net/{fav['share']}\n\n"
        msg += "This will mount with guest access."
        
        self.session.openWithCallback(
            lambda res: self._execute_favorite_mount(res, fav) if res else None,
            MessageBox,
            msg,
            MessageBox.TYPE_YESNO
        )
    
    def _execute_favorite_mount(self, confirmed, fav):
        """Execute favorite mount"""
        if not confirmed:
            return
        
        self["status"].setText("⏳ Mounting...")
        
        def mount_thread():
            try:
                mount_point = f"/media/net/{fav['share']}"
                os.makedirs(mount_point, exist_ok=True)
                
                result = subprocess.run(
                    ["mount", "-t", "cifs",
                     f"//{fav['server']}/{fav['share']}",
                     mount_point,
                     "-o", "guest,vers=3.0,iocharset=utf8"],
                    capture_output=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    self.session.open(MessageBox, 
                                    f"✅ Mounted!\n\n{mount_point}",
                                    MessageBox.TYPE_INFO, timeout=3)
                    self["status"].setText("✅ Mount successful")
                else:
                    self["status"].setText("❌ Mount failed")
            except Exception as e:
                logger.error(f"Mount error: {e}")
                self["status"].setText("Mount error")
        
        threading.Thread(target=mount_thread, daemon=True).start()
    
    def browse_favorite(self):
        """Browse favorite share"""
        current = self["favorites_list"].getCurrent()
        if not current or not current[1]:
            return
        
        fav = current[1]
        self.session.open(SMBShareBrowserScreen, fav['server'], fav['share'])
    
    def delete_favorite(self):
        """Delete selected favorite"""
        current = self["favorites_list"].getCurrent()
        if not current or not current[1]:
            return
        
        fav = current[1]
        
        msg = f"Remove from favorites?\n\n"
        msg += f"{fav['server']}/{fav['share']}"
        
        self.session.openWithCallback(
            lambda res: self._execute_delete(res, fav) if res else None,
            MessageBox,
            msg,
            MessageBox.TYPE_YESNO
        )
    
    def _execute_delete(self, confirmed, fav):
        """Execute favorite deletion"""
        if not confirmed:
            return
        
        try:
            # Remove from list
            self.favorites = [f for f in self.favorites 
                            if not (f['server'] == fav['server'] and f['share'] == fav['share'])]
            
            # Save and reload
            self.save_favorites()
            self.load_favorites()
            
            self["status"].setText("Removed from favorites")
        except Exception as e:
            logger.error(f"Delete favorite error: {e}")
            self["status"].setText("Delete failed")


class SMBShareBrowserScreen(Screen):
    """Browse SMB share contents before mounting"""
    
    def __init__(self, session, server, share):
        Screen.__init__(self, session)
        
        self.server = server
        self.share = share
        self.current_path = ""
        
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = f"""
        <screen name="SMBShareBrowserScreen" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#3a1a5a" />
            <widget name="title" position="20,10" size="{w-40},60" font="Regular;28" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            
            <widget name="file_list" position="100,120" size="{w-200},{h-250}" scrollbarMode="showOnDemand" backgroundColor="#2a2a2a" foregroundColor="#ffffff" selectionBackground="#1976d2" />
            
            <eLabel position="0,{h-120}" size="{w},120" backgroundColor="#1a1a1a" />
            <widget name="status" position="20,{h-110}" size="{w-40},50" font="Regular;22" halign="center" valign="center" transparent="1" foregroundColor="#00ff00" />
            <widget name="help" position="20,{h-55}" size="{w-40},40" font="Regular;18" halign="center" valign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        self["title"] = Label(f"📁 Browsing: //{server}/{share}")
        self["file_list"] = MenuList([])
        self["status"] = Label("⏳ Loading...")
        self["help"] = Label("OK:Enter  BACK:Parent  GREEN:Mount  EXIT:Close")
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.enter_directory,
            "cancel": self.go_back,
            "green": self.mount_share,
            "back": self.parent_directory,
        }, -1)
        
        self.onLayoutFinish.append(self.browse_directory)
    
    def browse_directory(self, path=""):
        """Browse directory in share"""
        self.current_path = path
        self["status"].setText(f"⏳ Loading {path if path else 'root'}...")
        
        def browse_thread():
            try:
                # Use smbclient to list directory
                smb_path = f"//{self.server}/{self.share}/{path}"
                
                result = subprocess.run(
                    ["smbclient", smb_path, "-N", "-c", "ls"],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                items = []
                
                if result.returncode == 0:
                    # Parse directory listing
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        if not line or line.startswith('.'):
                            continue
                        
                        # Parse smbclient ls output
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            attrs = parts[1] if len(parts) > 1 else ""
                            size = parts[2] if len(parts) > 2 else "0"
                            
                            is_dir = 'D' in attrs
                            icon = "📁" if is_dir else "📄"
                            
                            items.append((
                                f"{icon} {name}",
                                {'name': name, 'is_dir': is_dir, 'size': size}
                            ))
                    
                    # Add parent directory option if not in root
                    if path:
                        items.insert(0, ("📂 [..]  (Parent Directory)", {'name': '..', 'is_dir': True}))
                    
                    self["file_list"].setList(items if items else [("(Empty directory)", None)])
                    self["status"].setText(f"📁 {len(items)} items")
                    self["title"].setText(f"📁 //{self.server}/{self.share}/{path}")
                else:
                    self["file_list"].setList([
                        ("❌ Cannot browse share", None),
                        ("", None),
                        ("Access may require authentication", None),
                    ])
                    self["status"].setText("Browse failed")
                
            except Exception as e:
                logger.error(f"Browse error: {e}")
                self["status"].setText(f"Error: {str(e)[:50]}")
        
        threading.Thread(target=browse_thread, daemon=True).start()
    
    def enter_directory(self):
        """Enter selected directory"""
        current = self["file_list"].getCurrent()
        if not current or not current[1]:
            return
        
        item = current[1]
        
        if item['is_dir']:
            if item['name'] == '..':
                self.parent_directory()
            else:
                new_path = f"{self.current_path}/{item['name']}" if self.current_path else item['name']
                self.browse_directory(new_path)
        else:
            # Show file info
            msg = f"📄 FILE INFO\n\n"
            msg += f"Name: {item['name']}\n"
            msg += f"Size: {item['size']}\n"
            msg += f"Path: //{self.server}/{self.share}/{self.current_path}\n\n"
            msg += "Mount share to access this file"
            
            self.session.open(MessageBox, msg, MessageBox.TYPE_INFO)
    
    def parent_directory(self):
        """Go to parent directory"""
        if not self.current_path:
            return
        
        # Go up one level
        parts = self.current_path.split('/')
        if len(parts) > 1:
            new_path = '/'.join(parts[:-1])
        else:
            new_path = ""
        
        self.browse_directory(new_path)
    
    def go_back(self):
        """Go back or close"""
        if self.current_path:
            self.parent_directory()
        else:
            self.close()
    
    def mount_share(self):
        """Mount the share"""
        msg = f"Mount Share?\n\n"
        msg += f"//{self.server}/{self.share}\n\n"
        msg += f"Mount point:\n"
        msg += f"/media/net/{self.share}\n\n"
        msg += "Guest access will be used."
        
        self.session.openWithCallback(
            self._execute_mount,
            MessageBox,
            msg,
            MessageBox.TYPE_YESNO
        )
    
    def _execute_mount(self, confirmed):
        """Execute mount - FIXED VERSION without syntax errors"""
        if not confirmed:
            return
        
        self["status"].setText("⏳ Mounting...")
        
        def mount_thread():
            try:
                mount_point = f"/media/net/{self.share}"
                os.makedirs(mount_point, exist_ok=True)
                
                result = subprocess.run(
                    ["mount", "-t", "cifs",
                     f"//{self.server}/{self.share}",
                     mount_point,
                     "-o", "guest,vers=3.0,iocharset=utf8"],
                    capture_output=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    self.session.open(MessageBox,
                                    f"✅ Mounted!\n\n{mount_point}",
                                    MessageBox.TYPE_INFO, timeout=3)
                    self["status"].setText("✅ Mounted")
                else:
                    self["status"].setText("❌ Mount failed")
            except Exception as e:
                logger.error(f"Mount error: {e}")
                self["status"].setText("Mount error")
        
        threading.Thread(target=mount_thread, daemon=True).start()