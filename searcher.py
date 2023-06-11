from collections import defaultdict
from easysnmp import Session
import heapq
import os
import graphviz


# Global vars needed after
IPs = set()
routersInfo = dict()
routersIfs = dict()
routersExtIps = dict()
shortest_paths = dict()


""" Method used to retrieve all necessary info from the routers """


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

    # Getting the information of all interfaces
    for entry in description:
        intExtIps = list()
        if entry.oid == 'ifPhysAddress' and entry.value != '':  # Since physical address -> no loopbacks
            index = entry.oid_index
            mac = entry.value
            if session.get('ifAdminStatus.' + index).value == '1':  # Since value==1 -> no down interfaces
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
                        routerIfs.append((ip, netmask.value, speed.value))
                        intIp = ip
                        IPs.add(ip)
                    else:
                        intExtIps.append(ip)
                        print("Connected to: " + ip)
                        extIPs.add(ip)
                # Save connected IPs' pair
                routerPairExtIps.append((intIp, intExtIps))
                print()
    # Save router's info in global vars
    routersIfs[name] = routerIfs
    routersExtIps[name] = routerPairExtIps
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
    for router1, router2 in routers:
        router1ips = getIps(router1, routersIfs)
        router2ips = getIps(router2, routersIfs)
        all_ips.update(router1ips)
        all_ips.update(router2ips)
        # Save adjacent routers' IPs as connected (distance = 1)
        for ip1 in router1ips:
            for ip2 in router2ips:
                router_if[ip1].append(ip2)
                router_if[ip2].append(ip1)
    # Use Dijkstra's algorithm to get the shortest paths between all the IPs
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
    """ NO BORRAR: tinc mig apanyat el formateig del missatge com el vol el César pero per a una altra versió que mirava 
        routers no ip's, potser l'utilitzo si no li deixem talqual amb les ip's """
    """
    distances = {node: float('inf') for node in graph}
    distances[source] = 0

    routes = {node: [] for node in graph}
    queue = [(0, source, [])]
    while queue:
        dist, node, route = heapq.heappop(queue)
        if dist > distances[node]:
            continue
        for neighbor in graph[node]:
            new_dist = dist + graph[node][neighbor]
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                new_route = route + [neighbor]
                routes[neighbor] = new_route
                heapq.heappush(queue, (new_dist, neighbor, new_route))

    return distances, routes
    """


""" Method used to collect all ip's associated with every router """


def getIps(router, allrouters):
    ips = [pair[0] for pair in allrouters[router]]
    return ips


if __name__ == "__main__":
    IPs.add("11.0.5.2")  # we add our tap ip address, so it doesn't get checked
    recursiveSearch("11.0.5.1")  # ip our tap interface is connected to
    print("\n 1 - POLLING ALL THE ROUTERS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 1 - i/f info (for every router)
    print(routersIfs)
    print("\n 2 - GETTING THE ROUTING TABLES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 2 - routing table (for every router)
    print(routersInfo)

    # Apartat 4 - Graph related code
    edges = []
    net = graphviz.Digraph(filename="net.gv", comment='Network layout')

    switches=dict()
    switchId=0
    for router in routersExtIps:
        net.node(router, router)
    for routerId in routersExtIps.keys():
        intfs = routersExtIps[routerId]
        for intf in intfs:
            if(len(intf[1])>1):
                foundIp= False
                for switch, ips in switches.items():
                    if intf[0] in ips:
                        foundIp = True
                        net.edge(routerId,"S"+str(switchId), taillabel=intf[0], xlabel="", label="             ", arrowhead="none")
                if(not foundIp):
                        switches[switchId]=intf[1]
                        switchId+=1
                        net.edge(routerId,"S"+str(switchId), taillabel=intf[0],  xlabel="", label="             ", arrowhead="none")
            else:
                for extRouter in routersIfs.items():
                    for item in extRouter[1]:
                        if item[0] == intf[1][0]:
                            edges.append(((routerId, extRouter[0]), intf[1][0], intf[0]))
                            


    filtered_edges = []
    for edge in edges:
        if ((edge[0][1],edge[0][0]),edge[2], edge[1]) not in filtered_edges:
            filtered_edges.append((edge))
    for edge in filtered_edges:
        net.edge(*edge[0], headlabel=edge[1], taillabel=edge[2], xlabel="", label="             ", arrowhead="none")
    # T'he tret el render d'aqui per fer els prints d'apartats gucci, simplement està més abaix
    print("\n 3 - CREATING ROUTE SUMMARIES >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Apartat 3 - Shortest paths related code (4 abans perque fem el filtered_edges)
    routers = [pair[0] for pair in filtered_edges]
    shortest_paths = dijkstra(routers)

    for ip in shortest_paths:
        print(f"Shortests paths from {ip}: ")
        for target, intermediate in shortest_paths[ip].items():
            path = [target]
            while intermediate != ip:
                path.append(intermediate)
                intermediate = shortest_paths[ip][intermediate]
            path.append(ip)
            path.reverse()

            # route = routes[target]
            # route_str = ' -> '.join(route[:-1])
            # if distance > 1:
            #    withFirstIp = f"IPorig:{router} -> " + route_str
            #    parsedRoute = withFirstIp + " -> IPdest:" + route[-1]
            #    print(f"To {target}: {distance} ({parsedRoute})")
            # elif distance == 1:
            print(f"To {target}: {' -> '.join(path)}")
        print()

        # distance = 0 means same router
    print("\n 4 - PLOTTING THE NETWORK (pop-up window) >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    net.render('net.gv', view=True)
    print("\n 5 - MONITOR THE NETWORK >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    # Send snmp traps from routers using Cisco traps (ospf state-change neighbor-state-change)
    # When recievd, process, decode and print all trap info
        # No se si ens caldrà un bucle per esperar-se sempre a veure si rep o algo
    """ Això també estava al main original pero no se si ens cal 
    # Connexions between routers (by IP)
    print(routersExtIps)"""
