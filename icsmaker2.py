#!/usr/bin/python3
import socket
import requests
import bs4
import icalendar
from datetime import datetime
import os
import getpass
import http.server
import socketserver
import sys
import getopt
import base64
import time

my_url = "https://www.example.org"

class MyTCPServer(socketserver.TCPServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)


class MyRequestHandler (http.server.BaseHTTPRequestHandler) :
    # auxiliary methods
    def log_request(self, code='-', size='-'):
        """Log an accepted request. This is called by send_response()."""
        self.log_message('"%s" %s %s', self.requestline.split("?")[0], str(code), str(size))
    def do_AUTHHEAD(self):
        print("send header")
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"ical\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()        
    def produce_404(self):
        #send response code:
        self.send_response(404)
        #send headers:
        self.end_headers()        
        #main methods
    def produce_500(self):
        #send response code:
        self.send_response(500)
        #send headers:
        self.end_headers()        
        #main methods
    def do_HEAD(self):
        self.produce_404()
    def do_GET(self) :
        if self.headers.get('Authorization') == None:
            #lets check whether the auth is provided in the uri
            try:
                user = self.path.split("?")[1].split(",")[0]
                passwd = self.path.split("?")[1].split(",")[1]
                uricheck = self.path.split("?")[0]
            except:
                #couldn't find an alternate auth header
                self.do_AUTHHEAD()
                self.wfile.write('no auth header received'.encode('utf-8'))
                self.wfile.flush()
                #self.wfile.close()
                return                
            if uricheck == "/calendar.ics" :  
                try:
                    cal = getCalendar(user,passwd,3)
                except AuthException:
                    self.produce_500()
                    return    
                #send response code:
                self.send_response(200)
                #send headers:
                self.send_header('Content-Disposition','attachment; filename="calendar.ics"');                
                self.wfile.write(cal.to_ical())
                self.wfile.flush()
                return
            else:
                self.produce_404()
                return    
                
                
                
                
        #basic auth
        elif self.headers.get('Authorization')[:6] == 'Basic ':
            key = base64.b64decode(self.headers.get('Authorization')[6:])
            user=key.decode('utf-8').split(":")[0]
            passwd=key.decode('utf-8').split(":")[1]
            if self.path == "/calendar" :  
                try:
                    cal = getCalendar(user,passwd,30)
                except AuthException:
                    self.do_AUTHHEAD()
                    self.wfile.write('bad auth header received'.encode('utf-8'))
                    self.wfile.flush()
                    #self.wfile.close()
                    return
                #send response code:
                self.send_response(200)
                #send headers:
                self.wfile.write(cal.to_ical())
                self.wfile.flush()
                return
            else:
                self.produce_404()
                return

        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get('Authorization'))
            self.wfile.write('not authenticated'.encode('utf-8'))
            self.wfile.close()
        
class AuthException( Exception ):
    pass


class GetOutOfLoop( Exception ):
    pass

def web(port=8000,verbose=False):
    Handler = MyRequestHandler
    Handler.protocol_version = 'HTTP/1.0'
    Handler.close_connection = True
    httpdok = 0
    sys.stderr = open('/var/log/icsmaker2.log', 'a')
    sys.stdout = open('/var/log/icsmaker2.log', 'a')
    while(httpdok < 12):
        try:                         
            httpd = MyTCPServer(("0.0.0.0",int(port)), Handler)
            httpd.serve_forever()
            os._exit()
        except socket.error:
            httpdok += 1
            time.sleep(5)
    os._exit(0)
    
    
    
def cli(verbose=False):
    #get credentials
    user = input("Username:")
    passwd = getpass.getpass("Password for " + user + ":")
    cal = getCalendar(user,passwd,7)
    f = open('calendar.ics', 'wb')
    f.write(cal.to_ical())
    f.close()


def getCalendar(user,passwd,nbdays):
    cal = icalendar.Calendar()
    cal.add('prodid', '-//My calendar product//ical.example.com//')
    cal.add('version', '2.0')
    #pick up data from extranet
    s = requests.session()
    r1=s.get(my_url + '/wps/myportal/employee')
    r2 = s.post(my_url + "/my.policy", data={"username":user,"password":passwd})
    soup = bs4.BeautifulSoup(r2.content,"html.parser")
    link1 =  soup.form['action']
    if(len(link1) < 20):
        print("user auth "+user+" failed")
        sys.stdout.flush()
        sys.stderr.flush()
        raise AuthException
    else:
        print("user auth "+user+" success")
        sys.stdout.flush()
        sys.stderr.flush()
    r3=s.post(my_url+link1[:-16]+"&f5-sso-form=loginForm",data={"wps.portlets.userid":user,"password":"f5-sso-token"})
    soup = bs4.BeautifulSoup(r3.content,"html.parser")
    #get data from next nbdays, parse it, make events from it
    #soup.find_all("ul","info infoCal")
    for i in range(0,nbdays):
        #special handling for the current day
        if(i!=0):
            try:
                looplink = soup.find_all("li","next")[0].a['href']
            except IndexError:
                print("issue at day "+str(i)+" out of "+str(nbdays))
                print("couldn't scrape li next")
                break
            looprequest=s.get(my_url"+looplink)
            soup = bs4.BeautifulSoup(looprequest.content,"html.parser")
        else:
            soup = bs4.BeautifulSoup(r3.content,"html.parser")
        #parsing agenda
        try:
            ul = soup.find_all("ul","info infoCal")[-1]
        except IndexError:
            print("issue at day "+str(i)+" out of "+str(nbdays))
            print("couldn't scrape ul infocal")
            break
        li = ul.find_all("li")
        for j in li:
            event = icalendar.Event()
            try:
                #if there's no time field to be found, this isn't a valid meeting
                if not j.find_all("span","time"):
                    raise GetOutOfLoop
                span= j.find_all("span","time")
                for k in span:
                    #if the length of the timestamp is too short, it's not a valid meeting
                    if(len(k.find_all("span")[0].text)<10):
                        raise GetOutOfLoop
                    #print("time: "+k.find_all("span")[0].text)
                    fromtime = k.find_all("span")[0].text.split("-")[0].strip()
                    totime = k.find_all("span")[0].text.split("-")[1].strip()
                    date_object = datetime.now()
                    event.add('uid', date_object.isoformat()+"@ical.example.com")
                    event.add('dtstamp', date_object)                    
                    date_object = datetime.strptime(fromtime, '%a %b %d %X %Z %Y')
                    event.add('dtstart', date_object)
                    date_object = datetime.strptime(totime, '%a %b %d %X %Z %Y')
                    event.add('dtend', date_object)
                span = j.find_all("span","location")
                for k in span:
                    #print("location:" + k.find_all("span")[0].text)
                    event.add('location',k.find_all("span")[0].text)
                span = j.find_all("span","subject")
                for k in span:
                    #print("subject:" + k.find_all("span")[0].text)
                    event.add('summary',k.find_all("span")[0].text)
                #print("event added")
                cal.add_component(event)
            except GetOutOfLoop:
                #print("broken/empty entry, skipping it")
                pass
    return cal

def usage():
    print("valid args are -h , --cli, --web port")
    
def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hv", ["help","cli", "web=","verbose"])
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)
    verbose = False
    cliversion = False
    webversion = False
    port = 0
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("--web"):
            webversion = True
            port = int(a)
        elif o in ("--verbose"):
            verbose = True
        elif o in ("--cli"):
            cliversion = True
        else:
            assert False, "unhandled option"
    if cliversion == True:
        print("starting cli")
        cli(verbose=verbose)
    elif webversion == True:
        print("starting web on port "+str(port))
        web(port=port,verbose=verbose)
    else:
        print("unhandled stuff")
    
    
    
if __name__ == "__main__":
    main()