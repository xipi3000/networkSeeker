import heapq
from collections import defaultdict

from easysnmp import Session
import os
import graphviz

# Create an SNMP session to be used for all our requests
IPs = set()  # interfaces
routersInfo = dict()
routersIfs = dict()
routersExtIps = dict()


def recursiveSearch(sessionIp):
    print(sessionIp)  # show what router is getting asked for info
    extIPs = set()
    session = Session(hostname=sessionIp, community='rocom', version=2)
    description = session.walk('ifEntry')
    name = session.get('enterprises.9.2.1.3.0').value
    os.system(
        "snmptable -c rocom -v 2c " + sessionIp + " ipCidrRouteTable | awk  '{if(NR>3)print $1" "$2" "$4" "$6}' > "
                                                  "routeTable.log")
    f = open("routeTable.log", "r")
    routersInfo[name] = f.read()  # routing info for every router
    f.close()

    IPs.add(sessionIp)

    routerIfs = list()
    routerPairExtIps = list()

    for entry in description:
        intExtIps = list()

        if entry.oid == 'ifPhysAddress' and entry.value != '':

            index = entry.oid_index
            mac = entry.value
            if session.get('ifAdminStatus.' + index).value == '1':
                # print(session.get('ifDescr.'+index).value)
                allAddrs = session.walk('ipNetToPhysicalPhysAddress.' + index)
                intIp = ""

                for add in allAddrs:
                    addMac = add.value.encode('latin-1')
                    ip = add.oid_index[6:]

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

                routerPairExtIps.append((intIp, intExtIps))
                print()

    routersIfs[name] = routerIfs
    routersExtIps[name] = routerPairExtIps
    for ip in extIPs:
        if ip not in IPs:
            recursiveSearch(ip)


""" Method used to calculate the shortest path for every IP pair """


def dijkstra(network):
    # ara mateix funciona per cada router. HA de funcionar per cada IP de una interficie.
    # la idea es utilitzar el diccionari
    all_ips = set()
    router_if = defaultdict(list)
    for node1, node2 in network:
        router1ips = getIps(node1, routersIfs)
        router2ips = getIps(node2, routersIfs)
        all_ips.update(router1ips)
        all_ips.update(router2ips)
        for ip1 in router1ips:
            for ip2 in router2ips:
                router_if[ip1].append(ip2)
                router_if[ip2].append(ip1)
    shortest_paths = {}
    for source in all_ips:
        print("[D]Assigning values for shortest paths")
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
                distance = current_dist+1
                if distance<distances[neighbor_ip]:
                    distances[neighbor_ip] = distance
                    heapq.heappush(heap, (distance, neighbor_ip))
                    shortest_paths[source][neighbor_ip] = current_ip
    print("[D]shortest_paths contains: ")
    print(shortest_paths)
    return shortest_paths
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


def getIps(router, allrouters):
    ips = [pair[0] for pair in allrouters[router]]
    return ips


shortest_paths = {}
if __name__ == "__main__":
    IPs.add("5.0.3.2")  # we add our tap ip address, so it doesn't get checked
    recursiveSearch("5.0.3.1")  # ip our tap interface is connected to
    print(
        "====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    edges = []
    net = graphviz.Digraph(filename="net.gv", comment='Network layout')
    for router in routersExtIps:
        net.node(router, router)
    for routerId in routersExtIps.keys():
        intfs = routersExtIps[routerId]
        for intf in intfs:
            for v in routersIfs.items():
                for item in v[1]:
                    if item[0] == intf[1][0]:
                        edges.append((routerId, v[0]))
                        print(routerId + "->" + v[0])
    filtered_edges = []
    for edge in edges:
        if (edge[1], edge[0]) not in filtered_edges:
            filtered_edges.append(edge)
    for edge in filtered_edges:
        net.edge(*edge)
    net.render('net.gv', view=True)
    print(
        "====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    shortest_paths = dijkstra(filtered_edges)
    print("--------SHORTEST PATHS---------")
    print(shortest_paths)

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
    print(
        "====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(routersInfo)
    print(
        "====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(routersIfs)
    print(
        "====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(routersExtIps)
