import inotify.adapters
import threading
import time
from collections import defaultdict
from easysnmp import Session
import heapq
import os
import graphviz

# Global vars needed after
IPs = set()
routersInfo = dict()
routersIfs = dict()
routersIps = dict()
routersExtIps = dict()
shortest_paths = dict()

""" Method used to retrieve all necessary info from the routers """


class IntfPointingIps:
    def __init__(self, intfIP, pointingIps):
        self.intfIp = intfIP
        self.pointingIps = pointingIps


class IntfProperties:
    def __init__(self, intfIP, netmask, speed):
        self.intfIp = intfIP
        self.netmask = netmask
        self.speed = speed


def recursiveSearch(sessionIp):
    # Show which ip we'll be working with this iteration
    print(sessionIp)
    extIPs = set()
    # Create the session
    session = Session(hostname=sessionIp, community='rocom', version=2)
    description = session.walk('ifEntry')  # Get all interfaces
    name = session.get('enterprises.9.2.1.3.0').value
    # Getting the routing table info
    os.system(
        "snmptable -c rocom -v 2c " + sessionIp + " ipCidrRouteTable | awk  '{if(NR>3)print($1,$2,$4,$6)}' > routeTable.log")
    f = open("routeTable.log", "r")
    routersInfo[name] = f.read().split("\n")[:-1]  # Read routing table, separate lines, and clean last extra
    f.close()

    IPs.add(sessionIp)

    routerIfs = list()
    routerPairExtIps = list()
    routerIps = list()
    # Getting the information of all interfaces
    for entry in description:
        intExtIps = list()

        if entry.oid == 'ifPhysAddress' and entry.value != '':  # Since physical address -> no loopbacks
            index = entry.oid_index
            mac = entry.value
            if session.get('ifAdminStatus.' + index).value == '1':  # Since value==1 -> no down interfaces
                # Amb això descartem downs del propi router, no del que està connectat
                # Get who we're connected to
                allAddrs = session.walk('ipNetToPhysicalPhysAddress.' + index)
                intIp = ""

                for add in allAddrs:
                    addMac = add.value.encode('latin-1')
                    ip = add.oid_index[6:]
                    # Differentiate which ip we're working with
                    if mac.encode('latin-1') == addMac:
                        print("Inteface ip: " + ip)
                        netmask = session.get('ipAdEntNetMask.' + ip)
                        speed = session.get('1.3.6.1.2.1.2.2.1.5.' + index)
                        routerIfs.append(IntfProperties(ip, netmask.value, speed.value))
                        intIp = ip
                        routerIps.append(ip)
                        IPs.add(ip)
                    else:
                        intExtIps.append(ip)
                        print("Connected to: " + ip)
                        extIPs.add(ip)
                # Save connected IPs' pair
                routerPairExtIps.append(IntfPointingIps(intIp, intExtIps))
                print()
    # Save router's info in global vars
    routersIfs[name] = routerIfs
    routersExtIps[name] = routerPairExtIps
    routersIps[name] = routerIps
    # Next iteration (or end)
    for ip in extIPs:
        if ip not in IPs:
            recursiveSearch(ip)


""" Method used to calculate the shortest path for every IP pair """


def dijkstra(routers):
    # Instantiate vars
    all_ips = set()
    router_if = defaultdict(list)
    shortest_paths = dict()
    # Get all IPs
    for router in routers:
        router1ips = getIps(router)
        all_ips.update(router1ips)
        ips2=list()
        for connectedIps in routers[router]:
            for ip2 in connectedIps.pointingIps:
                ips2.append(ip2)
                # Save adjacent routers' IPs as connected (distance = 1)
                for ip1 in router1ips:
                    if ip2 not in router_if[ip1]:
                        router_if[ip1].append(ip2)
                    if ip1 not in router_if[ip2]:
                        router_if[ip2].append(ip1)
        all_ips.update(ips2)
    # Use Dijkstra's algorithm to get the shortest paths between all the IPs
    print(all_ips)
    for source in all_ips:
        shortest_paths[source] = {}
        visited = set()
        distances = {ip: float('inf') for ip in all_ips}
        distances[source] = 0
        heap = [(0, source)]
        while heap:
            current_dist, current_ip = heapq.heappop(heap)

            if current_ip in visited:
                continue
            visited.add(current_ip)

            for neighbor_ip in router_if[current_ip]:
                distance = current_dist + 1
                if distance < distances[neighbor_ip]:
                    distances[neighbor_ip] = distance
                    heapq.heappush(heap, (distance, neighbor_ip))
                    shortest_paths[source][neighbor_ip] = current_ip
    return shortest_paths


""" Method used to collect all ip's associated with a router """


def getIps(router):
    return routersIps[router]


def printTrap():
    with open("/etc/snmp/script/logs.txt", 'r') as f:
        for line in f:
            if line.startswith("trap information: "):
                print("Recieved trap:")
                print(line)


def waitForTrap(notifier):
    for event in notifier.event_gen(yield_nones=False):
        (_, type_names, path, filename) = event
        if "IN_MODIFY" in type_names and path == "/etc/snmp/script/logs.txt":
            printTrap()


def createGraph():
    edges = []
    net = graphviz.Digraph(filename="net.gv", comment='Network layout')

    switches = dict()
    switchId = 0
    for router in routersExtIps:
        net.node(router, label="",xlabel=router ,fontcolor="#c92f00",fontsize="20",fontname="bold",image="./router.png",width="1.2", height="0.8", fixedsize="true")


    for routerId in routersExtIps.keys():
        intfs = routersExtIps[routerId]
        for intf in intfs:
            if (len(intf.pointingIps) > 1):
                speed = 0
                for extRouter in routersIfs.items():
                    for item in extRouter[1]:
                        if item.intfIp == intf.intfIp:
                            speed = item.speed
                foundIp = False
                for switch, ips in switches.items():
                    if intf.intfIp in ips:
                        foundIp = True
                        net.edge(routerId, "S" + str(switchId), taillabel=intf.intfIp, xlabel="", label=speed + " bps",
                                 arrowhead="none")
                if (not foundIp):
                    switches[switchId] = intf.pointingIps
                    switchId += 1
                    net.node( "S" + str(switchId),label="",xlabel="S" + str(switchId),fontcolor="#c92f00",fontsize="20",fontname="bold",image="./switch.png",width="1.2", height="0.8", fixedsize="true")
                    net.edge(routerId, "S" + str(switchId), taillabel=intf.intfIp, xlabel="", label=speed + " bps",
                             arrowhead="none")
            else:
                for extRouter in routersIfs.items():
                    for item in extRouter[1]:

                        if item.intfIp == intf.pointingIps[0]:
                            edges.append(
                                (VectorInfo(routerId, extRouter[0], intf.intfIp, intf.pointingIps[0], item.speed)))
    filtered_edges = []
    for edge in edges:
        found = False
        for filtered_edge in filtered_edges:
            if (VectorInfo(edge.extRouter, edge.inRouter, edge.extIp, edge.inIp, edge.speed).equals(filtered_edge)):
                found = True
        if (not found):
            filtered_edges.append((edge))
    for edge in filtered_edges:
        print(edge.inRouter, edge.extRouter, edge.inIp, edge.speed)
        net.edge(edge.inRouter, edge.extRouter, headlabel=str(edge.extIp), taillabel=str(edge.inIp), xlabel="",
                 label=str(edge.speed) + " bps", arrowhead="none")
    return net, filtered_edges


class VectorInfo():
    def __init__(self, inRouter, extRouter, inIp, extIp, speed):
        self.inRouter = inRouter
        self.extRouter = extRouter
        self.inIp = inIp
        self.extIp = extIp
        self.speed = speed

    def equals(self, other):
        if (self.inRouter == other.inRouter and
                self.extRouter == other.extRouter and
                self.inIp == other.inIp and
                self.extIp == other.extIp and
                self.speed == other.speed):
            return True
        return False

def getRouterFromIp(ip):
    for k, v in routersIfs.items():
        for intfs in v:
            if(str(ip)==str(intfs.intfIp)):
               # print(ip)
                #print(k+" "+intfs.intfIp+" "+intfs.netmask+" "+intfs.speed)
                return k

if __name__ == "__main__":
    #notifier = inotify.adapters.Inotify()
    #notifier.add_watch("/etc/snmp/script/logs.txt")
    #waitForTrap(notifier)
    #thread = threading.Thread(target=printTrap)
    #thread.start()

    IPs.add("11.0.5.2")  # we add our tap ip address, so it doesn't get checked
    recursiveSearch("11.0.5.1")  # ip our tap interface is connected to
    print("\n 1 - POLLING ALL THE ROUTERS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 1 - i/f info (for every router)
    for k, value in routersIfs.items():
        for item in value:
            print(k+" "+item.intfIp+" "+item.netmask+" "+item.speed)
    print("\n 2 - GETTING THE ROUTING TABLES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 2 - routing table (for every router)
    print(routersInfo)

    # Apartat 4 - Graph related code
    net, filtered_edges = createGraph()
    print("\n 3 - CREATING ROUTE SUMMARIES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 3 - Shortest paths related code
    routers = [(item.inIp, item.extIp) for item in filtered_edges]
    print(routers)
    shortest_paths = dijkstra(routersExtIps)
    print(shortest_paths)
    for ip in shortest_paths:
        print(f"Shortests paths from {ip}({str(getRouterFromIp(ip))}): ")
        for target, intermediate in shortest_paths[ip].items():
            path = [target]
            while intermediate != ip:
                path.append(str(getRouterFromIp(intermediate)))
                intermediate = shortest_paths[ip][intermediate]
            
            path.append(str(getRouterFromIp(ip)))

            path.reverse()


            print(f"To {target}({str(getRouterFromIp(target))}): {' -> '.join(path)}({str(getRouterFromIp(target))})")
        print()

        # distance = 0 means same router
    print("\n 4 - PLOTTING THE NETWORK (pop-up window) >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")

    net.render('net.gv', view=True)
    print("\n 5 - MONITOR THE NETWORK >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Handled by the thread
