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
#For every router has its routing table
routingTables = dict()
#For every router has the IntfProperties for each interface
routersIfs = dict()

routersIps = dict()
#For every router has the IntfPointingIps for each interface
routersExtIps = dict()
shortest_paths = dict()
yourIp=""
seekingIp=""
""" Method used to retrieve all necessary info from the routers """

#It encapsulates the interface ip and its ip pair or multiple ips if connected with a switch
class IntfPointingIps:
    def __init__(self, intfIP, pointingIps):
        self.intfIp = intfIP
        self.pointingIps = pointingIps

#It encapsulates the interface with its information.
class IntfProperties:
    def __init__(self, intfIP, netmask, speed):
        self.intfIp = intfIP
        self.netmask = netmask
        self.speed = speed

#Searches all the specified network.
def recursiveSearch(sessionIp,debugging):
    # Show which ip we'll be working with this iteration
    if(debugging):
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
    routingTables[name] = f.read().split("\n")[:-1]  # Read routing table, separate lines, and clean last extra
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
                        if(debugging):print("Inteface ip: " + ip)
                        netmask = session.get('ipAdEntNetMask.' + ip)
                        speed = session.get('1.3.6.1.2.1.2.2.1.5.' + index)
                        routerIfs.append(IntfProperties(ip, netmask.value, speed.value))
                        intIp = ip
                        routerIps.append(ip)
                        IPs.add(ip)
                    else:
                        intExtIps.append(ip)
                        if(debugging):print("Connected to: " + ip)
                        extIPs.add(ip)
                # Save connected IPs' pair
                routerPairExtIps.append(IntfPointingIps(intIp, intExtIps))
                if(debugging):print()
    # Save router's info in global vars
    routersIfs[name] = routerIfs
    routersExtIps[name] = routerPairExtIps
    routersIps[name] = routerIps
    # Next iteration with a new thread for each (or end) 
    threads=[]
    for ip in extIPs:
        if ip not in IPs:
            thread = threading.Thread(target=recursiveSearch, args=(ip,debugging))
            thread.start()
            threads.append(thread)
    for thread in threads:
        thread.join()


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

#Gets all the ips from a router
def getIps(router):
    ips=[]
    for intf in routersIfs[router]:
        ips.append(intf.intfIp)
    return ips


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

#This function creates all the nodes and connections visible in the gv
def createGraph():
    edges = []
    net = graphviz.Digraph(filename="net.gv", comment='Network layout')
    switches = dict()
    switchId = 0
    #Creates all the router nodes
    for router in routersExtIps:
        net.node(router, label="",xlabel=router ,fontcolor="#c92f00",fontsize="20",fontname="bold",image="./router.png",width="1.2", height="0.8", fixedsize="true")

    #Creates the connection between the routers
    for routerId, intfs in routersExtIps.items():
        for intf in intfs:

            #If there are more than one external ips means that a switch like device is being used so it creates a switch node
            if (len(intf.pointingIps) > 1):
                speed = fromRouterGetIntf(intf.intfIp,routerId).speed
                foundIp = False
                
                #If the switch node has been created already just connect the nodes.
                for switch, ips in switches.items():
                    print(switches[switch])
                    if intf.intfIp in ips:
                        print(switch)
                        foundIp = True
                        net.edge(routerId, "S" + str(switch+1), taillabel=intf.intfIp, xlabel="", label=speed + " bps",
                                 arrowhead="none")
                #If the switch node hasn't been created yet it will create a new node, connect the edges and add to a dictionary the switchId with connected to it.
                if (not foundIp):
                    print(switches)
                    switches[switchId] = intf.pointingIps
                    switches[switchId].append(intf.intfIp)
                   
                    switchId += 1
                    net.node( "S" + str(switchId),label="",xlabel="S" + str(switchId),fontcolor="#c92f00",fontsize="20",fontname="bold",image="./switch.png",width="1.2", height="0.8", fixedsize="true")
                    net.edge(routerId, "S" + str(switchId), taillabel=intf.intfIp, xlabel="", label=speed + " bps",
                             arrowhead="none")
                    
            #If no switch like device is used
            else:
                #Gets the interface information and the external ip connected to it.
                interInfo = fromRouterGetIntf(intf.intfIp,routerId)
                extRouter = getRouterFromIp(intf.pointingIps[0])
                edges.append(
                    (VectorInfo(routerId, extRouter, intf.intfIp, intf.pointingIps[0], interInfo.speed)))

    #As the routes are repeated because 2 routers have the same connection information we remove those that are repeated.       
    filtered_edges = []
    for edge in edges:
        found = False
        for filtered_edge in filtered_edges:
            if (VectorInfo(edge.extRouter, edge.inRouter, edge.extIp, edge.inIp, edge.speed).equals(filtered_edge)):
                found = True
        if (not found):
            filtered_edges.append((edge))
    #Creates the visual representation of the finally achieved connections
    for edge in filtered_edges:
        net.edge(edge.inRouter, edge.extRouter, headlabel=str(edge.extIp), taillabel=str(edge.inIp), xlabel="",
                 label=str(edge.speed) + " bps", arrowhead="none")
    return net, filtered_edges

#This object encapsulates all the information required for each node connection in the visual graph.
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

#Given an ip and router returns its interface information
def fromRouterGetIntf(ip,router):
    for interface in routersIfs[router]:
        if(interface.intfIp==ip):
            return interface


#Given an ip returns to which ip is connected to 
def searchConnectedIp(ip):
    for k, v in routersExtIps.items():
        for intfs in v:
            for extIp in intfs.pointingIps:
                if(ip==extIp):
                    return intfs.intfIp
                
#If the users input is "y" then is true, else is false
def isDebugging(inputResult): 
    if(inputResult=="y"):
        return True
    return False

#Given an ip it returns the router from its interface belongs
def getRouterFromIp(ip):
    if(ip==yourIp):
        return "Your Device"
    for k, v in routersIfs.items():
        for intfs in v:
            if(ip==intfs.intfIp):

                return k
                

if __name__ == "__main__":
    #notifier = inotify.adapters.Inotify()
    #notifier.add_watch("/etc/snmp/script/logs.txt")
    #thread = threading.Thread(target=waitForTrap, args=(notifier,))
    #thread.start()

    #Get the ip address from input
    yourIp=""
    seekingIp=""
    debugging=False
    yourIp = input("Insert your device interface IP connected to the target network: ")
    seekingIp = input("Insert the ip address you wanna search in the target network: ")
    debugging = isDebugging(input("Debug the network search? (y/n)"))
    
    IPs.add(yourIp)  # we add our tap ip address, so it doesn't get checked
    print("Searching...")
    recursiveSearch(seekingIp,debugging)  # ip our tap interface is connected to
    
    print("\n 1 - POLLING ALL THE ROUTERS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 1 - i/f info (for every router)
    for k, value in routersIfs.items():
        print("Device: "+k)
        for item in value:
            print("\tIp: "+item.intfIp+" Netmask: "+item.netmask+" Speed: "+item.speed+"bps")
        print()
    print("\n 2 - GETTING THE ROUTING TABLES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 2 - routing table (for every router)
    for device, deviceIntfs in routingTables.items():
        print("Device:" + device)
        for intf in deviceIntfs:
            print("\t"+intf)
        print()

    # Apartat 4 - Graph related code
    net, filtered_edges = createGraph()
    print("\n 3 - CREATING ROUTE SUMMARIES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 3 - Shortest paths related code
    routers = [(item.inIp, item.extIp) for item in filtered_edges]
    #print(routers)
    shortest_paths = dijkstra(routersExtIps)
    #print(shortest_paths)
    for ip in shortest_paths:
        print(f"Shortests paths from {ip}({str(getRouterFromIp(ip))}): ")
        for target, intermediate in shortest_paths[ip].items():
            path = [target +"("+str(getRouterFromIp(target))+")"]
            while intermediate != ip:
                path.append(str(getRouterFromIp(intermediate)))
                intermediate = shortest_paths[ip][intermediate]

            path.append(ip +"("+str(getRouterFromIp(ip))+")")

            path.reverse()


            print(f"To {target}({str(getRouterFromIp(target))}): {' -> '.join(path)} ")
        print()

        # distance = 0 means same router
    print("\n 4 - PLOTTING THE NETWORK (pop-up window) >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")

    net.render('net.gv', view=True)
    print("\n 5 - MONITOR THE NETWORK >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Handled by the thread
