from easysnmp import Session
import os
# Create an SNMP session to be used for all our requests
IPs=set()
routersInfo=dict()
routersIfs=dict()
routersExtIps=dict()
def recursiveSearch(sessionIp):
    print(sessionIp)
    extIPs=set()
    session = Session(hostname=sessionIp, community='public', version=2)
    description = session.walk('ifEntry')
    name=session.get('enterprises.9.2.1.3.0').value
    os.system("snmptable -c public -v 2c "+sessionIp+" ipCidrRouteTable | awk  '{if(NR>3)print $1" "$2" "$4" "$6}' > routeTable.log" )
    f = open("routeTable.log","r")
    routersInfo[name]=f.read()
    f.close()
           
    
    IPs.add(sessionIp)

    routerIfs=list()
    routerPairExtIps=list()

    for entry in description:
        intExtIps=list()
        
        if(entry.oid=='ifPhysAddress'  and entry.value !=''  ):
            
            index = entry.oid_index
            mac= entry.value
            if(session.get('ifAdminStatus.'+index).value=='1'):
                    #print(session.get('ifDescr.'+index).value)
                allAddrs=session.walk('ipNetToPhysicalPhysAddress.'+index)
                intIp=""
                
                for add in allAddrs:
                    addMac = add.value.encode('latin-1')
                    ip = add.oid_index[6:]
                    if(mac.encode('latin-1')==addMac):
                        
                        print("Internal: "+ip)
                        netmask= session.get('ipAdEntNetMask.'+ip)
                        speed= session.get('1.3.6.1.2.1.2.2.1.5.'+index)
                        routerIfs.append((ip,netmask.value,speed.value))
                        intIp=ip
                        IPs.add(ip)
                    else: 
                        intExtIps.append(ip)
                        print("External: "+ip)
                        extIPs.add(ip)
                        
                routerPairExtIps.append((intIp,intExtIps))
                print()
                
    
    routersIfs[name]=routerIfs
    routersExtIps[name]=routerPairExtIps
    for ip in extIPs:
        if(ip not in IPs):
             recursiveSearch(ip)      


if __name__ == "__main__":
    
    IPs.add("11.0.5.2")
    recursiveSearch("11.0.5.1")
    print(routersInfo)
    print(routersIfs)
    print(routersExtIps)
    