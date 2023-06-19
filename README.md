# Installing requirements:

First of all, install all the requirements listed in the requirements.txt. 

You can do it with the command: 
```shell
pip install -r requirements.txt
```

# Activating monitorization: 
 
In order to set up the trap catcher, you'll have to follow these steps:
  
First, go to /etc/snmp and create a new directory called "script":
```shell
cd /etc/snmp
sudo mkdir script
```

Then, go to the "extra_files" directory provided with the project and copy 
all .conf files to /etc/snmp, and the "trap_handler" file 
into the new script directory:
```shell
cd /<path-to-project>/extra_files
sudo cp snmp.conf /etc/snmp
sudo cp snmpd.conf /etc/snmp
sudo cp snmptrapd.conf /etc/snmp
sudo cp trap_handler /etc/snmp/extra_files
```
  
and don't forget to give execution privileges to the script! 
  
And while you're there, create an empty file called logs.txt
```shell
cd /etc/snmp/script
sudo chmod +x trap_handler
sudo touch logs.txt
```

Now you're free to start the services (and if you can't, try installing them first with sudo apt-get install)
```shell
sudo service snmpd start
sudo service snmptrapd start
```

# Searcher.py usage:
 When you write "python3 searcher.py" on the terminal you want to run our program, you'll be promted to tell which IP you're using to connect to the network, and then you'll be asked for the ip of the first router you want to poll information from. 

If you want to actively see which router is being polled and the connections it has, you can activate the debug option. 
If you just want to see the resulting information of the complete network, feel free to not   activate it.
