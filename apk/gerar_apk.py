"""Gera uma versão nova do APK do RAFICOU! a partir do APK anterior.

O que muda:
  • troca assets/index.html pela versão nova (com a aba Ofertas);
  • adiciona a permissão de internet no AndroidManifest.xml (sem ela o app não baixa as ofertas);
  • sobe a versão (versionCode/versionName);
  • monta o zip alinhado e assina com APK Signature Scheme v2.

Uso:
  python gerar_apk.py --base RAFICOU-1.1.apk --html ../site/index.html --saida RAFICOU-1.2.apk \
      --chave raficou-chave.p12 --senha "SUA SENHA" [--feed https://usuario.github.io/raficou-robo/]

Se o arquivo da chave não existir, uma chave nova é criada nele. Guarde esse arquivo: as próximas
versões precisam ser assinadas com a mesma chave para atualizar o app sem desinstalar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import struct
import sys
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apkv2  # noqa: E402

PERMISSAO = "android.permission.INTERNET"
ID_ATRIBUTO_NAME = 0x01010003
NS_ANDROID = "http://schemas.android.com/apk/res/android"


# ---------------------------------------------------------------- manifesto binário (AXML)
def _ler_pool(buf: bytes, off: int):
    _, hsz, tam, n, nestilos, flags, ini, _ = struct.unpack_from("<HHIIIIII", buf, off)
    if nestilos:
        raise ValueError("manifesto com estilos no pool de strings: não suportado")
    utf8 = bool(flags & 0x100)
    offs = struct.unpack_from(f"<{n}I", buf, off + hsz)
    strs = []
    for o in offs:
        p = off + ini + o
        if utf8:
            p += 2 if buf[p] & 0x80 else 1
            k = buf[p]; p += 1
            if k & 0x80:
                k = ((k & 0x7F) << 8) | buf[p]; p += 1
            strs.append(buf[p:p + k].decode("utf-8"))
        else:
            k = struct.unpack_from("<H", buf, p)[0]; p += 2
            if k & 0x8000:
                k = ((k & 0x7FFF) << 16) | struct.unpack_from("<H", buf, p)[0]; p += 2
            strs.append(buf[p:p + 2 * k].decode("utf-16le"))
    return strs, flags, tam


def _escrever_pool(strs: list[str], flags: int) -> bytes:
    utf8 = bool(flags & 0x100)
    dados, offs = bytearray(), []
    for s in strs:
        offs.append(len(dados))
        if utf8:
            b = s.encode("utf-8")
            for k in (len(s), len(b)):
                dados += bytes([0x80 | (k >> 8), k & 0xFF]) if k > 0x7F else bytes([k])
            dados += b + b"\0"
        else:
            u = s.encode("utf-16le")
            k = len(u) // 2
            dados += (struct.pack("<HH", 0x8000 | (k >> 16), k & 0xFFFF) if k > 0x7FFF else struct.pack("<H", k)) + u + b"\0\0"
    while len(dados) % 4:
        dados += b"\0"
    ini = 28 + 4 * len(strs)
    cab = struct.pack("<HHIIIIII", 0x0001, 28, ini + len(dados), len(strs), 0, flags, ini, 0)
    return cab + struct.pack(f"<{len(strs)}I", *offs) + bytes(dados)


def _pedacos(buf: bytes):
    off = 8
    while off < len(buf):
        tipo, _, tam = struct.unpack_from("<HHI", buf, off)
        yield off, tipo, tam
        off += tam


def ajustar_manifesto(axml: bytes, codigo_versao: int, nome_versao: str) -> bytes:
    pool_off = next(o for o, t, _ in _pedacos(axml) if t == 0x0001)
    strs, flags, pool_tam = _ler_pool(axml, pool_off)
    mapa_off = next(o for o, t, _ in _pedacos(axml) if t == 0x0180)
    mapa_tam = struct.unpack_from("<I", axml, mapa_off + 4)[0]
    mapa = struct.unpack_from(f"<{(mapa_tam - 8) // 4}I", axml, mapa_off + 8)
    i_name = next(i for i, r in enumerate(mapa) if r == ID_ATRIBUTO_NAME)

    def indice(s):
        if s in strs:
            return strs.index(s)
        strs.append(s)
        return len(strs) - 1

    corpo = bytearray(axml[pool_off + pool_tam:])     # mapa de recursos + nós
    base = pool_off + pool_tam
    ja_tem = PERMISSAO in strs and any(
        t == 0x0102 and strs[struct.unpack_from("<I", axml, o + 20)[0]] == "uses-permission"
        and strs[struct.unpack_from("<I", axml, o + 36 + 8)[0]] == PERMISSAO
        for o, t, _ in _pedacos(axml) if t == 0x0102)

    i_vn, i_up, i_perm, i_ns = indice(nome_versao), indice("uses-permission"), indice(PERMISSAO), strs.index(NS_ANDROID)
    insercao = None
    for o, tipo, tam in _pedacos(axml):
        if o < base:
            continue
        r = o - base
        if tipo == 0x0102:
            nome = strs[struct.unpack_from("<I", axml, o + 20)[0]]
            a_ini, a_tam, a_qtd = struct.unpack_from("<HHH", axml, o + 24)
            for k in range(a_qtd):
                a = o + 16 + a_ini + k * a_tam
                an = strs[struct.unpack_from("<I", axml, a + 4)[0]]
                if nome == "manifest" and an == "versionCode":
                    struct.pack_into("<I", corpo, r + 16 + a_ini + k * a_tam + 16, codigo_versao)
                if nome == "manifest" and an == "versionName":
                    struct.pack_into("<I", corpo, r + 16 + a_ini + k * a_tam + 8, i_vn)
                    struct.pack_into("<I", corpo, r + 16 + a_ini + k * a_tam + 16, i_vn)
        if tipo == 0x0103 and insercao is None and strs[struct.unpack_from("<I", axml, o + 20)[0]] == "uses-sdk":
            insercao = r + tam

    if not ja_tem:
        linha = 2
        inicio = struct.pack("<HHIIIIIHHHHHH", 0x0102, 16, 56, linha, 0xFFFFFFFF, 0xFFFFFFFF, i_up, 20, 20, 1, 0, 0, 0)
        atributo = struct.pack("<IIIHBBI", i_ns, i_name, i_perm, 8, 0, 0x03, i_perm)
        fim = struct.pack("<HHIIIII", 0x0103, 16, 24, linha, 0xFFFFFFFF, 0xFFFFFFFF, i_up)
        corpo[insercao:insercao] = inicio + atributo + fim

    novo_pool = _escrever_pool(strs, flags)
    total = 8 + (pool_off - 8) + len(novo_pool) + len(corpo)
    return struct.pack("<HHI", 0x0003, 8, total) + axml[8:pool_off] + novo_pool + bytes(corpo)


# ---------------------------------------------------------------- zip alinhado
def montar_zip(arquivos: list[tuple[str, bytes, bool]]) -> bytes:
    """arquivos: (nome, dados, comprimir). Entradas sem compressão ficam alinhadas em 4 bytes."""
    import io
    mem = io.BytesIO()
    data = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(mem, "w") as z:
        for nome, dados, comprimir in arquivos:
            info = zipfile.ZipInfo(nome, date_time=data)
            info.create_system = 0
            info.external_attr = 0
            if comprimir:
                info.compress_type = zipfile.ZIP_DEFLATED
            else:
                info.compress_type = zipfile.ZIP_STORED
                inicio_dados = mem.tell() + 30 + len(nome.encode())
                falta = (-inicio_dados) % 4
                if falta:
                    falta += 4 if falta < 4 else 0   # cabeçalho extra precisa de pelo menos 4 bytes
                    info.extra = struct.pack("<HH", 0xD935, falta - 4) + b"\0" * (falta - 4)
            z.writestr(info, dados)
    return mem.getvalue()


def conferir_alinhamento(apk: bytes) -> None:
    import io
    z = zipfile.ZipFile(io.BytesIO(apk))
    for i in z.infolist():
        nl, el = struct.unpack_from("<HH", apk, i.header_offset + 26)
        ini = i.header_offset + 30 + nl + el
        if i.compress_type == zipfile.ZIP_STORED and ini % 4:
            raise ValueError(f"{i.filename} desalinhado")
    if z.getinfo("resources.arsc").compress_type != zipfile.ZIP_STORED:
        raise ValueError("resources.arsc precisa ficar sem compressão")
    if z.testzip():
        raise ValueError("zip corrompido")


# ---------------------------------------------------------------- chave
def chave_e_certificado(caminho: Path, senha: str):
    if caminho.exists():
        chave, cert, _ = pkcs12.load_key_and_certificates(caminho.read_bytes(), senha.encode())
        return chave, cert, False
    chave = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RAFICOU!"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Rafic"),
                      x509.NameAttribute(NameOID.COUNTRY_NAME, "BR")])
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(days=1))
            .not_valid_after(agora + dt.timedelta(days=365 * 30))
            .sign(chave, hashes.SHA256()))
    caminho.write_bytes(pkcs12.serialize_key_and_certificates(b"raficou", chave, cert, None,
                                                              BestAvailableEncryption(senha.encode())))
    return chave, cert, True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="APK anterior (ex.: RAFICOU-1.1.apk)")
    ap.add_argument("--html", required=True, help="index.html novo")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--chave", required=True, help="arquivo .p12 da chave (criado se não existir)")
    ap.add_argument("--senha", required=True)
    ap.add_argument("--versao", default="1.2")
    ap.add_argument("--codigo", type=int, default=3, help="versionCode (tem que subir a cada versão)")
    ap.add_argument("--feed", default="", help="endereço do robô para já vir configurado no app")
    a = ap.parse_args()

    html = Path(a.html).read_text(encoding="utf-8")
    if a.feed:
        alvo = "const FEED_PADRAO = '';"
        assert alvo in html, "não achei FEED_PADRAO no index.html"
        html = html.replace(alvo, "const FEED_PADRAO = %s;" % repr(a.feed.strip()).replace('"', "'"))

    base = zipfile.ZipFile(a.base)
    arquivos = []
    for info in base.infolist():
        nome = info.filename
        if nome.startswith("META-INF/"):
            continue
        dados = base.read(nome)
        if nome == "AndroidManifest.xml":
            dados = ajustar_manifesto(dados, a.codigo, a.versao)
        elif nome == "assets/index.html":
            dados = html.encode("utf-8")
        comprimir = not (nome == "resources.arsc" or nome.endswith(".png"))
        arquivos.append((nome, dados, comprimir))
    ordem = {"AndroidManifest.xml": 0, "classes.dex": 1, "resources.arsc": 2}
    arquivos.sort(key=lambda x: (ordem.get(x[0], 3), x[0]))

    sem_assinatura = montar_zip(arquivos)
    conferir_alinhamento(sem_assinatura)
    chave, cert, nova = chave_e_certificado(Path(a.chave), a.senha)
    apk = apkv2.assinar(sem_assinatura, chave, cert)
    info = apkv2.verificar(apk)
    Path(a.saida).write_bytes(apk)
    print(f"APK gerado: {a.saida} ({len(apk) // 1024} KB) · versão {a.versao} ({a.codigo})")
    print(f"Assinatura v2: {info['assinatura']}, resumo: {info['resumo']}, certificado: {info['certificado']}")
    if nova:
        print(f"Chave NOVA criada em {a.chave}. Guarde esse arquivo e a senha.")


if __name__ == "__main__":
    main()
