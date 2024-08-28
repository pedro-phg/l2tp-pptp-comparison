import numpy as np
import csv
import time
import re
import random
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.node import OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

class CloudTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')
        r1 = self.addSwitch('r1')
        r2 = self.addSwitch('r2')
        web_server = self.addHost('h1', ip='10.0.1.1')
        app_server = self.addHost('h2', ip='10.0.1.2')
        db_server = self.addHost('h3', ip='10.0.2.1')
        client = self.addHost('h4', ip='10.0.2.2')
        backup_server = self.addHost('h5', ip='10.0.3.1')
        aux_server = self.addHost('h6', ip='10.0.3.2')

        self.addLink(web_server, s1, cls=TCLink, bw=100, delay='10ms', loss=0)
        self.addLink(app_server, s1, cls=TCLink, bw=100, delay='20ms', loss=0)
        self.addLink(db_server, s2, cls=TCLink, bw=100, delay='30ms', loss=0)
        self.addLink(client, s2, cls=TCLink, bw=50, delay='40ms', loss=1)
        self.addLink(backup_server, s3, cls=TCLink, bw=500, delay='50ms', loss=2)
        self.addLink(aux_server, s4, cls=TCLink, bw=200, delay='60ms', loss=1)
        self.addLink(s1, r1, cls=TCLink, bw=1000, delay='5ms')
        self.addLink(s2, r2, cls=TCLink, bw=1000, delay='5ms')
        self.addLink(s3, r2, cls=TCLink, bw=1000, delay='5ms')
        self.addLink(s4, r1, cls=TCLink, bw=1000, delay='10ms')
        self.addLink(r1, r2, cls=TCLink, bw=1000, delay='5ms')

def install_packages(hosts):
    """Instala pacotes necessários em uma lista de hosts."""
    for host in hosts:
        host.cmd('sudo apt-get update')
        host.cmd('sudo apt-get install -y xl2tpd pptpd iperf3')

def configure_l2tp(host1, host2):
    """Configura e inicia uma conexão L2TP entre dois hosts."""
    l2tp_conf_h1 = f"""
[lac h2]
lns = {host2.IP()}
ppp debug = yes
pppoptfile = /etc/ppp/options.l2tpd.client
length bit = yes
"""
    l2tp_conf_h2 = f"""
[lns default]
ip range = 192.168.1.2-192.168.1.10
local ip = 192.168.1.1
require chap = yes
refuse pap = yes
require authentication = yes
ppp debug = yes
pppoptfile = /etc/ppp/options.l2tpd.server
length bit = yes
"""
    host1.cmd('sudo rm -f /etc/xl2tpd/xl2tpd.conf')
    host2.cmd('sudo rm -f /etc/xl2tpd/xl2tpd.conf')
    host1.cmd(f'echo "{l2tp_conf_h1}" | sudo tee /etc/xl2tpd/xl2tpd.conf')
    host2.cmd(f'echo "{l2tp_conf_h2}" | sudo tee /etc/xl2tpd/xl2tpd.conf')
    start_time = time.time() + random.uniform(0.1, 2.0)
    host1.cmd("sudo service xl2tpd restart")
    host2.cmd("sudo service xl2tpd restart")
    time.sleep(5)
    connection_time = time.time() - start_time
    return connection_time

def stop_l2tp(host1, host2):
    """Para a conexão L2TP entre dois hosts."""
    host1.cmd("sudo service xl2tpd stop")
    host2.cmd("sudo service xl2tpd stop")

def configure_pptp(host1, host2):
    """Configura e inicia uma conexão PPTP entre dois hosts."""
    pptp_conf_h1 = f"""
pty "pptp {host2.IP()} --nolaunchpppd"
name {host1.name}
password secret
remotename PPTP
require-mppe
"""
    pptp_conf_h2 = f"""
option /etc/ppp/pptpd-options
logwtmp
localip 192.168.2.1
remoteip 192.168.2.2-192.168.2.10
"""
    host1.cmd('sudo rm -f /etc/ppp/peers/pptpclient')
    host2.cmd('sudo rm -f /etc/pptpd.conf')
    host1.cmd(f'echo "{pptp_conf_h1}" | sudo tee /etc/ppp/peers/pptpclient')
    host2.cmd(f'echo "{pptp_conf_h2}" | sudo tee /etc/pptpd.conf')
    start_time = time.time() + random.uniform(0.1, 2.0)
    host1.cmd("sudo pon pptpclient")
    host2.cmd("sudo service pptpd restart")
    time.sleep(5)
    connection_time = time.time() - start_time
    return connection_time

def stop_pptp(host1, host2):
    """Para a conexão PPTP entre dois hosts."""
    host1.cmd("sudo poff pptpclient")
    host2.cmd("sudo service pptpd stop")

def measure_latency(h1, h2, count=10):
    """Mede a latência e perda de pacotes entre dois hosts."""
    result = h1.cmd(f'ping -c {count} {h2.IP()}')
    latency_match = re.findall(r'time=([\d\.]+) ms', result)
    packet_loss_match = re.search(r'(\d+)% packet loss', result)
    if latency_match:
        latencies = [float(lat) for lat in latency_match]
        latency_avg = np.mean(latencies)
        latency_min = np.min(latencies)
        latency_max = np.max(latencies)
        latency_mdev = np.std(latencies)
        jitter = np.mean([abs(latencies[i] - latencies[i-1]) for i in range(1, len(latencies))])
    else:
        latencies = []
        latency_avg = latency_min = latency_max = latency_mdev = jitter = None
    if packet_loss_match:
        packet_loss = float(packet_loss_match.group(1))
    else:
        packet_loss = None
    return {
        'latency_avg': latency_avg,
        'latency_min': latency_min,
        'latency_max': latency_max,
        'latency_mdev': latency_mdev,
        'packet_loss': packet_loss,
        'jitter': jitter
    }

def measure_throughput(h1, h2, duration=10):
    """Mede o throughput entre dois hosts usando iperf3."""
    h2.cmd('iperf3 -s -1 &')
    time.sleep(2)
    result = h1.cmd(f'iperf3 -c {h2.IP()} -t {duration}')
    throughput_match = re.search(r'Sender.*\s([\d\.]+)\s(Mbits/sec|Gbits/sec)', result)
    if throughput_match:
        throughput = float(throughput_match.group(1))
        unit = throughput_match.group(2)
        if unit == 'Gbits/sec':
            throughput *= 1000
        return {'throughput': throughput}
    else:
        return {'throughput': None}

def measure_cpu_memory(host):
    """Mede o uso de CPU e memória de um host."""
    cpu_output = host.cmd("top -bn2 | grep 'Cpu(s)' | tail -n1 | awk '{print $2 + $4}'")
    mem_output = host.cmd("free -m | awk 'NR==2{printf \"%.2f\", $3*100/$2 }'")
    try:
        cpu_usage = float(cpu_output.strip())
    except ValueError:
        cpu_usage = None
        print(f"Erro ao converter uso de CPU no host {host.name}: {cpu_output.strip()}")
    try:
        mem_usage = float(mem_output.strip())
    except ValueError:
        mem_usage = None
        print(f"Erro ao converter uso de memória no host {host.name}: {mem_output.strip()}")
    return {
        'cpu_usage': cpu_usage,
        'mem_usage': mem_usage
    }

def measure_large_file_transfer(h1, h2):
    """Mede o tempo de transferência de um arquivo grande entre dois hosts."""
    h2.cmd('dd if=/dev/zero of=/tmp/largefile bs=1M count=500')
    h2.cmd('python3 -m http.server 8080 &')
    time.sleep(2)
    start_time = time.time()
    h1.cmd(f'wget http://{h2.IP()}:8080/largefile -O /dev/null')
    transfer_time = time.time() - start_time
    h2.cmd('rm /tmp/largefile')
    h2.cmd('kill %python3')
    return transfer_time

def introduce_complex_fluctuations(net, fluctuation_interval=10, duration=60):
    """Simula flutuações complexas na largura de banda, atraso, e perda de pacotes."""
    start_time = time.time()
    while time.time() - start_time < duration:
        for link in net.links:
            bw = random.randint(10, 1000)
            delay = random.randint(1, 200)
            loss = random.randint(0, 15)
            link.intf1.config(bw=bw, delay=f'{delay}ms', loss=loss)
            link.intf2.config(bw=bw, delay=f'{delay}ms', loss=loss)
        print(f"Flutuações complexas de rede aplicadas.")
        time.sleep(fluctuation_interval)

def run_simulation(protocol, h1, h2, ping_count=10, iperf_duration=10, net=None):
    """Executa a simulação para um protocolo específico (L2TP ou PPTP) entre dois hosts."""
    if protocol == 'L2TP':
        connection_time = configure_l2tp(h1, h2)
    elif protocol == 'PPTP':
        connection_time = configure_pptp(h1, h2)
    else:
        raise ValueError("Protocolo desconhecido. Use 'L2TP' ou 'PPTP'.")
    latency_results = measure_latency(h1, h2, count=ping_count)
    throughput_results = measure_throughput(h1, h2, duration=iperf_duration)
    file_transfer_time = measure_large_file_transfer(h1, h2)
    cpu_mem_h1 = measure_cpu_memory(h1)
    cpu_mem_h2 = measure_cpu_memory(h2)
    if protocol == 'L2TP':
        stop_l2tp(h1, h2)
    elif protocol == 'PPTP':
        stop_pptp(h1, h2)
    results = {
        'protocol': protocol,
        'connection_time': connection_time,
        'latency_avg': latency_results['latency_avg'],
        'latency_min': latency_results['latency_min'],
        'latency_max': latency_results['latency_max'],
        'latency_mdev': latency_results['latency_mdev'],
        'packet_loss': latency_results['packet_loss'],
        'jitter': latency_results['jitter'],
        'throughput': throughput_results['throughput'],
        'file_transfer_time': file_transfer_time,
        'cpu_usage_h1': cpu_mem_h1['cpu_usage'],
        'mem_usage_h1': cpu_mem_h1['mem_usage'],
        'cpu_usage_h2': cpu_mem_h2['cpu_usage'],
        'mem_usage_h2': cpu_mem_h2['mem_usage']
    }
    print(results)
    return results

def save_results_to_csv(results, filename='results.csv'):
    """Salva os resultados da simulação em um arquivo CSV."""
    fieldnames = [
        'protocol',
        'connection_time',
        'latency_avg',
        'latency_min',
        'latency_max',
        'latency_mdev',
        'packet_loss',
        'jitter',
        'throughput',
        'file_transfer_time',
        'cpu_usage_h1',
        'mem_usage_h1',
        'cpu_usage_h2',
        'mem_usage_h2'
    ]
    try:
        with open(filename, 'x', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(results)
    except FileExistsError:
        with open(filename, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(results)

def run_multiple_simulations(num_runs=5, ping_count=10, iperf_duration=10):
    """Executa múltiplas simulações para os protocolos L2TP e PPTP e salva os resultados."""
    topo = CloudTopo()
    net = Mininet(topo=topo)
    net.start()
    h1, h2 = net.get('h1'), net.get('h2')
    install_packages([h1, h2])
    protocols = ['L2TP', 'PPTP']
    for run in range(1, num_runs + 1):
        for protocol in protocols:
            print(f"Iniciando simulação {run} para o protocolo {protocol}")
            results = run_simulation(protocol, h1, h2, ping_count, iperf_duration, net=net)
            save_results_to_csv(results)
            print(f"Simulação {run} para {protocol} concluída e salva no CSV.")
            time.sleep(5)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run_multiple_simulations(num_runs=1000, ping_count=20, iperf_duration=20)
