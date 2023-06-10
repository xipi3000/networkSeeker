from easysnmp import Session
import os
from netaddr import IPAddress
import sys

import graphviz
# Create an SNMP session to be used for all our requests
IPs = set()

routersInfo = dict()
routersIfs = dict()
routersExtIps = dict()
graph = dict() # for dijsktra


def recursiveSearch(sessionIp):
    print(sessionIp)
    extIPs = set()
    session = Session(hostname=sessionIp, community='rocom', version=2)
    description = session.walk('ifEntry')
    name = session.get('enterprises.9.2.1.3.0').value
    os.system(
        "snmptable -c rocom -v 2c " + sessionIp + " ipCidrRouteTable | awk  '{if(NR>3)print $1" "$2" "$4" "$6}' > "
                                                  "routeTable.log")
    f = open("routeTable.log", "r")
    routersInfo[name] = f.read()
    f.close()
           
    
    IPs.add(sessionIp)

    routerIfs=list()
    routerPairExtIps=list()

    for entry in description:
        intExtIps = list()

        if entry.oid == 'ifPhysAddress' and entry.value != '':

            index = entry.oid_index
            mac = entry.value
            if session.get('ifAdminStatus.' + index).value == '1':  # discards down
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
                        
                routerPairExtIps.append((intIp,intExtIps))
                print()

    routersIfs[name] = routerIfs
    routersExtIps[name] = routerPairExtIps
    for ip in extIPs:
        if ip not in IPs:
            recursiveSearch(ip)


""" Method used to calculate the shortest path for every IP pair """
def dijkstra(graph, source):
    print(graph)
    distances = {ip: sys.maxsize for ip in graph}
    # keys = ip's, values = weight's, items = pairs of those
    distances[source] = 0
    visited = set()

    while len(visited) < len(graph):
        current_node = min((ip for ip in graph if ip not in visited), key=distances.get)
        visited.add(current_node)

        for neighbor, weight in graph[current_node].items():
            if distances[current_node] + weight < distances[neighbor]:
                distances[neighbor] = distances[current_node] + weight
                print(f"UPDATED DISTANCE!!!!!!! ({distances[neighbor]})")

    return distances


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
    print("====================================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    for routerIp in IPs:
        graph[IPAddress(routerIp)] = {IPAddress(ip): 1 for ip in IPs if ip != routerIp}

    distances = dijkstra(graph, "5.0.3.1")
    #print(distances)

    for destination, distance in distances.items():
        path = [destination]
        current = destination
        while current != "5.0.3.1":
            for neighbor, weight in graph[current].items():
                if distances[current]-weight == distances[neighbor]:
                    path.append(neighbor)
                    current = neighbor
                    # break
        path.reverse()
        print(f"Shortest path from 5.0.3.1 to {destination}: {path}")


    # print(distances)
    print(routersInfo)
    print(routersIfs)
    print(routersExtIps)
