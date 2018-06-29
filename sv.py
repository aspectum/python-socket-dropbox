import socket
import threading
import pickle
import os
import shutil
import time
from pathlib import Path

svroot = os.getcwd()                    # Diretorio raiz do servidor
sharedfolder = svroot + '/' + 'shared'  # Diretorio da pasta compartilhada
loginsDB = svroot + "/logins.txt"       # Arquivo com os logins
logfile = svroot + "/log.txt"           # Arquivo de log
buffer_size = 4096                      # Tamanho do buffer de recebimento do socket
segment_size = 2048                     # Tamanho dos segmentos de arquivo a serem enviados/recebidos
foldersinuse = []                       # Lista com as pastas em uso para sincronizar entre clientes
log = open(logfile, 'w')                # Abertura do arquivo de log

# Monta e envia um pacote
def ssend(c, header, seq, currPath, data):
    seq += 1
    dataC = (header, [seq], [currPath], data)
    pktC = pickle.dumps(dataC)
    c.send(pktC)

# Recebe um pacote
def srecv(c):
    pktC = c.recv(buffer_size)
    dataC = pickle.loads(pktC)
    seq = dataC[1][0]
    currPath = dataC[2][0]
    return (seq, currPath, dataC)

# Mostra na tela uma mensagem e escreve no log
def mensagem(msg, addr, usr):
    adendo = "<%s:%s> (%s): " % (addr[0], addr[1], usr)
    newmsg = adendo + msg
    print(newmsg)
    log.write(newmsg+"\n")
    return msg

# Realiza o arredondamento para cima (na hora de calcular o numero de pacotes para enviar um arquivo)
def ceil(n):
    res = int(n)
    return res if res == n or n < 0 else res+1

# Cria um diretorio
def mkdir(c, nomePasta, seq, currPath, basePath, addr, usr):
    # Esse teste por '~' aparece varias vezes no codigo
    # Isso e porque '~' e opcional e referencia a pasta base do usuario
    if nomePasta[0] == '~':
        nomePasta = nomePasta.replace('~', basePath)
    try:
        os.makedirs(nomePasta)
        msg = mensagem("Diretorio %s criado" % nomePasta, addr, usr)
        ssend(c, ['r', 'md'], seq, currPath, [msg])
        return 1
    except Exception as e:  # Ja existe pasta com o mesmo nome

        ssend(c, ['r', 'e'], seq, currPath, [e])
        mensagem(str(e), addr, usr)
        return 0

# Faz as preparacacoes para receber um arquivo
def pre_recebearq(c, dataC, seq, currPath, basePath, addr, usr):
    nomearq = dataC[3][0]
    tmpdst = dataC[3][1]
    numpkts = dataC[3][2]
    dst = tmpdst
    if tmpdst[0] == '~':
        dst = tmpdst.replace('~', basePath)
    novonome = dst + '/' + nomearq
    try:    # Abre (cria) o arquivo que vai receber os segmentos
        arq = open(novonome, 'xb')
    except Exception as e:  # Arquivo ja existe

        ssend(c, ['r', 'e'], seq, currPath, [e])
        mensagem(str(e), addr, usr)
        return
    # Essa pacote avisa o cliente que o arquivo ja foi aberto
    # e esta preparado para receber os segmentos
    ssend(c, ['r', 'ul'], seq, currPath, [])
    # Chama a funcao que efetivamente recebe o arquivo
    recebearq(c, arq, numpkts, seq, currPath, addr)

    arq.close()

# Recebe os segmentos do cliente e os escreve no arquivo aberto em pre_recebearq
def recebearq(c, arq, numpkts, seq, currPath, addr):
    i = 0
    while True:
        # Recebe o segmento
        (seq, currPath, dataC) = srecv(c)
        # Escreve o segmento
        seg = dataC[3][0]
        arq.write(seg)
        i = i+1

        # Confirma a escrita e pede o proximo segmento
        ssend(c, ['rv'], seq, currPath, [])
        if i == numpkts:    # O contador compara com o valor conhecido de numero de pacotes
            break

# Faz as preparacoes para enviar um arquivo
def pre_enviaarq(c, nomearq, dst, seq, currPath, addr, usr):
    try:
        tam = os.path.getsize(nomearq)      # Pega o tamanho do arquivo
        numpkts = ceil(tam/segment_size)    # Calcula o numero de segmentos necessarios para enviar o arquivo
    except Exception as e:  # Arquivo nao existe
        ssend(c, ['r', 'e'], seq, currPath, [e])
        mensagem(str(e), addr, usr)
        return
    try:
        arq = open(nomearq, 'rb')
    except Exception as e:  # Arquivo nao existe
        ssend(c, ['r', 'e'], seq, currPath, [e])
        mensagem(str(e), addr, usr)
        return

    # O objeto a ser enviado e um arquivo
    # Conseguiu abrir o arquivo de destino
    # Informacoes da transferencia
    ssend(c, ['r', 'dl', 'aq'], seq, currPath, [nomearq, numpkts, dst])
    (seq, currPath, dataC) = srecv(c)
    if dataC[0][0] == 'r':  # Checa a resposta do cliente
        if dataC[0][1] == 'dl':  # Tudo OK, pode enviar
            enviaarq(c, arq, seq, currPath, addr, usr)
            arq.close()
        elif dataC[0][1] == 'e':    # Algum erro conhecido
            errormsg = dataC[3][0]
            mensagem(errormsg, addr, usr)
            arq.close()
            return

# Envia os segmentos do arquivo aberto em pre_enviaarq para o cliente
def enviaarq(c, arq, seq, currPath, addr, usr):
    seg = arq.read(segment_size)
    while seg:                      # Envia o segmento para o cliente
        ssend(c, ['sd'], seq, currPath, [seg])
        (seq, currPath, dataC) = srecv(c)
        # Checa a resposta do cliente
        if dataC[0][0] == 'rv':     # Tudo certo, continua enviando
            pass
        seg = arq.read(segment_size)

# Recebe os arquivos e cria as pastas de um diretorio sendo "enviado" pelo cliente
def recebeDir(c, dataC, seq, currPath, basePath, addr, usr):
    nomedir = dataC[3][0]
    # Cria a pasta base (o proprio diretorio sendo "enviado")
    if not mkdir(c, nomedir, seq, currPath, basePath, addr, usr):
        return
    while 1:    # O loop da transferencia inteira
        (seq, currPath, dataC) = srecv(c)
        if dataC[0][0] == 'sd':
            if dataC[0][1] == 'aq':         # Resposta esperada
                pass
        elif dataC[0][0] == 'r':
            if dataC[0][1] == 'ul':         # Condicao de saida, fim da transferencia
                break
        while 1:                            # Loop que recebe todos os arquivos de um diretorio
            (seq, currPath, dataC) = srecv(c)
            if dataC[0][0] == 'ul':
                if dataC[0][1] == 'aq':     # Ainda tem mais arquivos para receber
                    pass
            elif dataC[0][0] == 'sd':
                if dataC[0][1] == 'dr':     # Acabou os arquivos, agora vamos para as pastas
                    break
            pre_recebearq(c, dataC, seq, currPath, basePath, addr, usr)   # Inicia o recebimento do arquivo
        while 1:                            # Loop da transferencia (criacao) das pastas de um diretorio
            (seq, currPath, dataC) = srecv(c)
            if dataC[0][0] == 'sd':
                if dataC[0][1] == 'dr':     # Ainda tem pastas para receber
                    pass
                elif dataC[0][1] == 'aq':   # Acabaram as pastas
                    break
            dirname = dataC[3][0]
            mkdir(c, dirname, seq, currPath, basePath, addr, usr)  # Cria a pasta

# Envia os arquivos e pastas de um diretorio para o cliente
def enviaDir(c, diretorio, seq, currPath, basePath, addr, usr):
    # O objeto a ser enviado e um diretorio
    # Envia o nome da pasta base
    diretorio = diretorio.replace(basePath + '/', '')
    tmpdir = diretorio
    if '/' in diretorio:
        dirsplit = diretorio.split('/')
        tmpdir = dirsplit[-1]
    tmpdir = diretorio.replace(tmpdir, '')
    psdir = diretorio.replace(tmpdir, '')
    ssend(c, ['r', 'dl', 'dr'], seq, currPath, [psdir])
    (seq, currPath, dataC) = srecv(c)
    # Aparentemente ele nao da o os.walk se o processo estiver dentro da pasta. Eu volto pra currPath no fim da funcao
    os.chdir(basePath)
    # Ve se tudo esta certo e a pasta foi criada
    if dataC[0][0] == 'r':
        if dataC[0][1] == 'md':    # Tudo certo
            pass
        elif dataC[0][1] == 'e':    # Provavelmente ja existe pasta com o mesmo nome
            errormsg = dataC[3][0]
            mensagem(errormsg, addr, usr)
            return
    # Itera por todas as subpastas do diretorio
    for root, dirs, files in os.walk(diretorio):

        ssend(c, ['sd', 'aq'], seq, currPath, [])
        time.sleep(0.05)
        for nomearquivo in files:   # Os arquivos do diretorio atual
            novonome = basePath + '/' + root + '/' + nomearquivo
            psdir = root.replace(tmpdir, '')
            pre_enviaarq(c, novonome, psdir, seq, currPath, addr, usr)  # Inicia o envio do arquivo atual
        # Finalizou o envio dos arquivos
        ssend(c, ['sd', 'dr'], seq, currPath, [])
        time.sleep(0.05)
        for nomePasta in dirs:    # As pastas do diretorio atual
            diret = root + '/' + nomePasta
            psdir = diret.replace(tmpdir, '')
            # Envia o nome da pasta atual para ser criada a correspondente no cliente
            ssend(c, ['sd', 'dr'], seq, currPath, [psdir])
            time.sleep(0.05)
            # Pega o retorno do mkdir, que nunca vai ser erro aqui
            (seq, currPath, dataC) = srecv(c)
        # Acabaram as pastas, agora vai para um novo diretorio
        ssend(c, ['sd', 'aq'], seq, currPath, [])
        time.sleep(0.05)
    # Acabaram os diretorios, termina a transferencia
    ssend(c, ['r', 'dl'], seq, currPath, [])
    time.sleep(0.05)
    os.chdir(currPath)

# PedroBOX Protocol v2, ou PBP
# Recebe o pacote inicial, interpreta o cabecalho e executa a operacao
def PBP(c, dataC, seq, userPath, currPath, basePath, usr, addr):
    # Para prevenir conflitos entre clientes distintos logados com o mesmo usuario
    global foldersinuse
    os.chdir(currPath)          # Vai no diretorio correto daquele cliente

    # Os if's checam o cabecalho e determinam a operacao
    if dataC[0][0] == 'ls':     # Lista os arquivos e pastas
        # Gera uma lista com os arquivos e pastas do diretorio atual
        dirlist = os.listdir(".")
        ssend(c, ['r', 'ls'], seq, currPath, dirlist)
    elif dataC[0][0] == 'cd':   # Muda o diretorio atual
        dst = dataC[3][0]
        if dst[0] == '~':
            dst = dst.replace('~', basePath)
        if '#shared' in dst:
            dst = dst.replace('#shared', sharedfolder)
        if '#user' in dst:
            dst = dst.replace('#user', userPath)
        if dst == ".." and currPath == basePath:    # Impede o cliente de sair do diretorio de usuario
            msg = mensagem("Erro, nao pode sair do diretorio base", addr, usr)
            ssend(c, ['r', 'e'], seq, currPath, [msg])
        else:
            try:
                oldPath = currPath
                os.chdir(dst)   # Muda de diretorio
                currPath = os.getcwd()
                mensagem("Acessou o diretorio %s" % currPath, addr, usr)
                # Atualiza a pasta atual do usuario
                foldersinuse.remove(oldPath)
                foldersinuse.append(currPath)
                # Confirmacao
                ssend(c, ['r', 'cd'], seq, currPath, [])
            except Exception as e:  # Diretorio nao existe
                ssend(c, ['r', 'e'], seq, currPath, [e])
                mensagem(str(e), addr, usr)
    elif dataC[0][0] == 'mv':   # Mover arquivo
        filename = dataC[3][0]
        tmpdst = dataC[3][1]
        tmpnome = filename
        novonome = filename
        if '/' in filename:     # Evita problemas com mv pasta1/pasta2/arq pasta3. Esse if pega apenas 'arq', que e o nome do arquivo
            nomesplit = filename.split('/')
            tmpnome = nomesplit[-1]
        if tmpdst[0] == '~':
            dst = tmpdst.replace('~', basePath)
            dst = dst + '/' + tmpnome
        else:
            dst = tmpdst + '/' + tmpnome
        if filename[0] == '~':
            novonome = filename.replace('~', basePath)
        if '#shared' in dst:
            dst = dst.replace('#shared', sharedfolder)
        if '#shared' in novonome:
            novonome = novonome.replace('#shared', sharedfolder)
        if '#user' in dst:
            dst = dst.replace('#user', userPath)
        if '#user' in novonome:
            novonome = novonome.replace('#user', userPath)
        if any(novonome in diret for diret in foldersinuse):
            msg = mensagem("Erro, diretorio %s nao pode ser movido pois esta em uso" % filename, addr, usr)
            ssend(c, ['r', 'e'], seq, currPath, [msg])
            return
        if tmpdst == '..':  # Ele pode mover um arquivo para o diretorio pai
            if currPath == basePath:    # Nao pode fazer isso se estiver no diretorio base do usuario
                msg = mensagem("Erro, nao pode mover o arquivo para fora do diretorio base", addr, usr)
                ssend(c, ['r', 'e'], seq, currPath, [msg])
            else:
                parentDir = Path(currPath).parent   # Diretorio pai
                try:
                    shutil.move(novonome, parentDir)    # Move o arquivo
                    mensagem("Arquivo %s movido para o diretorio superior" % filename, addr, usr)
                    # Confirmacao
                    ssend(c, ['r', 'mv'], seq, currPath, [])
                except Exception as e:  # Arquivo nao existe
                    ssend(c, ['r', 'e'], seq, currPath, [e])
                    mensagem(str(e), addr, usr)
        else:
            try:
                shutil.move(novonome, dst)  # Move o arquivo
                mensagem("Arquivo %s movido para %s" % (filename, tmpdst), addr, usr)
                ssend(c, ['r', 'mv'], seq, currPath, [])
            except Exception as e:  # Arquivo ou diretorio destino nao existe
                ssend(c, ['r', 'e'], seq, currPath, [e])
                mensagem(str(e), addr, usr)
    elif dataC[0][0] == 'rm':   # Remove arquivo ou diretorio
        tmptoBeDeleted = dataC[3][0]
        toBeDeleted = tmptoBeDeleted
        if tmptoBeDeleted[0] == '~':
            toBeDeleted = tmptoBeDeleted.replace('~', basePath)
        else:
            toBeDeleted = currPath + '/' + tmptoBeDeleted
        isfile = os.path.isfile(toBeDeleted)
        isdir = os.path.isdir(toBeDeleted)
        if isfile == False and isdir == False:  # Nao e arquivo nem diretorio, logo nao existe
            msg = mensagem("Erro, arquivo ou diretorio %s nao existe" % tmptoBeDeleted, addr, usr)
            ssend(c, ['r', 'e'], seq, currPath, [msg])
        else:
            if isfile == True:  # E arquivo
                try:
                    os.remove(toBeDeleted)  # Remove arquivo
                    mensagem("Arquivo %s excluido" % tmptoBeDeleted, addr, usr)
                    ssend(c, ['r', 'rm'], seq, currPath, [])
                except Exception as e:
                    ssend(c, ['r', 'e'], seq, currPath, [e])
                    mensagem(str(e), addr, usr)
            else:   # E pasta
                if any(toBeDeleted in diret for diret in foldersinuse):
                    msg = mensagem("Erro, diretorio %s nao pode ser excluido pois esta em uso" % tmptoBeDeleted, addr, usr)
                    ssend(c, ['r', 'e'], seq, currPath, [msg])
                    return
                try:
                    # Remove a pasta (e tudo dentro dela)
                    shutil.rmtree(toBeDeleted)
                    mensagem("Diretorio %s excluido" % tmptoBeDeleted, addr, usr)
                    ssend(c, ['r', 'rm'], seq, currPath, [])
                except Exception as e:
                    ssend(c, ['r', 'e'], seq, currPath, [e])
                    mensagem(str(e), addr, usr)
    elif dataC[0][0] == 'md':   # Cria uma pasta
        dirname = dataC[3][0]
        mkdir(c, dirname, seq, currPath, basePath, addr, usr)
    elif dataC[0][0] == 'ul':   # Upload (do cliente para o servidor)
        # Se e arquivo ou diretorio e chama a funcao correspondente
        if dataC[0][1] == 'aq':
            pre_recebearq(c, dataC, seq, currPath, basePath, addr, usr)
        elif dataC[0][1] == 'dr':
            recebeDir(c, dataC, seq, currPath, basePath, addr, usr)
    elif dataC[0][0] == 'dl':   # Donwload (do servidor para o cliente)
        nomearq = dataC[3][0]
        novonome = nomearq
        if nomearq[0] == '~':
            novonome = nomearq.replace('~', basePath)
        novonome = os.path.abspath(novonome)
        isfile = os.path.isfile(novonome)
        isdir = os.path.isdir(novonome)
        if isfile == False and isdir == False:  # Nao e arquivo ou pasta, logo nao existe
            msg = mensagem("Erro, arquivo ou diretorio %s nao existe" % novonome, addr, usr)
            ssend(c, ['r', 'e'], seq, currPath, [msg])
        else:   # Chama a funcao de envio de arquivo ou de diretorio
            if isfile == True:
                pre_enviaarq(c, novonome, [], seq, currPath, addr, usr)
            else:
                enviaDir(c, novonome, seq, currPath, basePath, addr, usr)
                pass

# Autenticacao do cliente
def signInSv(c, addr, dataC):
    seq = 0     # Numero de sequencia temporario

    msg = "<%s:%s> Tentando autenticar" % addr
    print(msg)
    usr = dataC[3][0]
    psw = dataC[3][1]
    # Procura na lista de cadastros pelo username recebido
    with open(loginsDB, 'r') as f:
        if f.mode == 'r':
            linhas = f.readlines()
            flag = 0
            for x in linhas:
                y = x.split(',')
                if y[0] == usr:     # Encontrou
                    flag = 1
                    correctPsw = y[1].rstrip()  # Guarda a senha correspondente
                    break
    if flag == 0:           # Usuario desconhecido
        msg = "<%s:%s> Erro, username nao cadastrado: %s" % (
            addr[0], addr[1], usr)
        print(msg)
        ssend(c, ['r', 'e', 'un'], seq, [], [])
        return (0, usr)
    # Usuario existe
    if psw != correctPsw:   # Senha errada
        msg = "<%s:%s> Erro, senha errada para o usuario %s" % (
            addr[0], addr[1], usr)
        print(msg)
        ssend(c, ['r', 'e', 'pn'], seq, [], [])
        return (0, usr)
    # Logado com sucesso
    msg = "<%s:%s> Autenticacao realizada com sucesso" % (addr[0], addr[1])
    print(msg)
    # Envia confirmacao para o cliente
    ssend(c, ['r', 'si'], seq, [], [])
    os.chdir(usr)   # Entra no diretorio do usuario
    return (1, usr)

# Cadastro no servidor
def signUpSv(c, dataC, addr):
    seq = 0

    msg = "<%s:%s> Tentando cadastrar" % (addr[0], addr[1])
    print(msg)
    usr = dataC[3][0]
    psw = dataC[3][1]
    msg = "<%s:%s> Username escolhido: %s" % (addr[0], addr[1], usr)
    print(msg)
    while True:
        with open(loginsDB, 'r') as f:
            if f.mode == 'r':
                linhas = f.readlines()
                flag = 0
                for x in linhas:
                    y = x.split(',')
                    if y[0] == usr:
                        flag = 1
                        break
        if flag == 0:       # Usuario valido
            break
        msg = "<%s:%s> Username ja esta em uso: %s" % (addr[0], addr[1], usr)
        print(msg)
        ssend(c, ['r', 'e', 'ue'], seq, [], [])
        return (0, usr)
    newCadastro = usr + ',' + psw   # Insere no arquivo de logins o novo cadastro
    with open(loginsDB, 'a') as f:
        if f.mode == 'a':
            f.write("\n")
            f.write(newCadastro)
    msg = "<%s:%s> Cadastrou o usuario: %s" % (addr[0], addr[1], usr)
    print(msg)
    ssend(c, ['r', 'su'], seq, [], [])
    os.makedirs("./" + usr)     # Cria o diretorio de usuario
    os.chdir("./" + usr)        # Entra no diretorio de usuario

    return (1, usr)

# Login no servidor
def loginSv(c, addr):
    global log
    os.chdir(svroot)
    dataC = srecv(c)[2]
    if dataC[0][0] == 'q':  # Opcao sair
        mensagem("Conexao encerrada", addr, '?')
        c.close()
        return (0, '')
    elif dataC[0][0] == 'su':   # Opcao cadastro
        ret = signUpSv(c, dataC, addr)
        if ret[0]:  # Cadastro com sucesso
            return (1, ret[1])
        else:       # Cadastro falhou
            mensagem("Falha no cadastro, conexao encerrada", addr, '?')
            c.close()
            return (0, '')
    elif dataC[0][0] == 'si':   # Opcao autenticacao
        ret = signInSv(c, addr, dataC)
        if ret[0]:  # Autenticou com sucesso
            return (1, ret[1])
        else:       # Autenticacao falhou
            mensagem("Falha na autenticacao, conexao encerrada", addr, '?')
            c.close()
            return (0, '')

# Thread de um cliente
def connthread(c, addr, usr):
    global foldersinuse, log

    seq = 0                             # Inicializa o numero de sequencia
    userPath = os.getcwd()              # Diretorio do usuario
    currPath = os.getcwd()              # Diretorio atual
    basePath = userPath                 # Diretorio base atual
    foldersinuse.append(currPath)       # Atualiza a pasta em uso
    mensagem("Sessao iniciada", addr, usr)
    msg = "Bem vindo, " + usr + "! Para ver os comandos digite 'ajuda'"
    ssend(c, ['p'], seq, currPath, [svroot, msg])
    while True:         # Loop principal da conexao
        pktC = c.recv(buffer_size)  # Recebe o pacote do cliente
        if not pktC:    # Caso o cliente desconecte
            mensagem("Conexao encerrada", addr, usr)
            break
        dataC = pickle.loads(pktC)
        seq = dataC[1][0]
        currPath = dataC[2][0]
        PBP(c, dataC, seq, userPath, currPath, basePath, usr, addr) # Chama a funcao do protocolo
        currPath = os.getcwd()
        if str(sharedfolder) in str(currPath):
            basePath = sharedfolder
        else:
            basePath = userPath
    c.close()

def Main():
    host = ""
    port = 12345
    # Inicializa o socket
    socketServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socketServer.bind((host, port))
    print("Socket bound to port ", port)
    socketServer.listen(5)      # Quantidade maxima de clientes simultaneos
    print("Socket listening")
    while True:
        c, addr = socketServer.accept() # Aceita uma nova conexao

        print('Conectado com: <%s:%s>' % addr)
        ret = loginSv(c, addr)
        if ret[0]:      # Tenta fazer o login
            # Inicia o thread do cliente
            threading.Thread(target=connthread, args=(c, addr, ret[1])).start()
    socketServer.close()

if __name__ == '__main__':
    Main()

log.close()