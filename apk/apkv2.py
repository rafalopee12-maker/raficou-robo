"""Assinatura APK v2 (APK Signature Scheme v2) e verificação, em Python puro + cryptography."""
from __future__ import annotations

import hashlib
import struct

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

MAGICO = b"APK Sig Block 42"
ID_V2 = 0x7109871A
ALG_RSA_SHA256 = 0x0103
MB = 1 << 20


def _lp(b: bytes) -> bytes:
    return struct.pack("<I", len(b)) + b


def _eocd(apk: bytes) -> int:
    i = apk.rfind(b"PK\x05\x06", max(0, len(apk) - 65557))
    if i < 0:
        raise ValueError("fim do zip (EOCD) não encontrado")
    return i


def _cd_offset(apk: bytes, eocd: int) -> int:
    return struct.unpack_from("<I", apk, eocd + 16)[0]


def _digest(secoes: list[bytes]) -> bytes:
    pedacos = []
    for s in secoes:
        for i in range(0, len(s), MB):
            c = s[i:i + MB]
            pedacos.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(c)) + c).digest())
    return hashlib.sha256(b"\x5a" + struct.pack("<I", len(pedacos)) + b"".join(pedacos)).digest()


def assinar(apk: bytes, chave, certificado: x509.Certificate) -> bytes:
    """Recebe um zip sem bloco de assinatura e devolve o APK assinado (v2)."""
    eocd = _eocd(apk)
    cd = _cd_offset(apk, eocd)
    conteudo, diretorio, fim = apk[:cd], apk[cd:eocd], apk[eocd:]
    resumo = _digest([conteudo, diretorio, fim])

    cert_der = certificado.public_bytes(serialization.Encoding.DER)
    spki = chave.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    dados = (_lp(_lp(struct.pack("<I", ALG_RSA_SHA256) + _lp(resumo)))
             + _lp(_lp(cert_der))
             + _lp(b""))
    assinatura = chave.sign(dados, padding.PKCS1v15(), hashes.SHA256())
    signatario = _lp(dados) + _lp(_lp(struct.pack("<I", ALG_RSA_SHA256) + _lp(assinatura))) + _lp(spki)
    valor = _lp(_lp(signatario))
    par = struct.pack("<Q", 4 + len(valor)) + struct.pack("<I", ID_V2) + valor
    tam = len(par) + 8 + 16
    bloco = struct.pack("<Q", tam) + par + struct.pack("<Q", tam) + MAGICO

    fim = bytearray(fim)
    struct.pack_into("<I", fim, 16, cd + len(bloco))
    return conteudo + bloco + diretorio + bytes(fim)


def verificar(apk: bytes) -> dict:
    """Confere o bloco v2 como o Android faz: resumos das três seções e assinatura RSA."""
    eocd = _eocd(apk)
    cd = _cd_offset(apk, eocd)
    if apk[cd - 16:cd] != MAGICO:
        raise ValueError("APK sem bloco de assinatura v2")
    tam = struct.unpack_from("<Q", apk, cd - 24)[0]
    inicio = cd - tam - 8
    if struct.unpack_from("<Q", apk, inicio)[0] != tam:
        raise ValueError("tamanhos do bloco não batem")
    p, fim_pares = inicio + 8, cd - 24
    v2 = None
    while p < fim_pares:
        n = struct.unpack_from("<Q", apk, p)[0]
        ident = struct.unpack_from("<I", apk, p + 8)[0]
        if ident == ID_V2:
            v2 = apk[p + 12:p + 8 + n]
        p += 8 + n
    if v2 is None:
        raise ValueError("bloco sem assinatura v2")

    def ler(buf, pos):
        n = struct.unpack_from("<I", buf, pos)[0]
        return buf[pos + 4:pos + 4 + n], pos + 4 + n

    signatarios, _ = ler(v2, 0)
    signatario, _ = ler(signatarios, 0)
    dados, q = ler(signatario, 0)
    assinaturas, q = ler(signatario, q)
    spki, _ = ler(signatario, q)
    chave_pub = serialization.load_der_public_key(spki)
    ass, _ = ler(assinaturas, 0)
    alg = struct.unpack_from("<I", ass, 0)[0]
    sig, _ = ler(ass, 4)
    resultado = {"algoritmo": hex(alg)}
    if alg == ALG_RSA_SHA256:
        chave_pub.verify(sig, dados, padding.PKCS1v15(), hashes.SHA256())
    elif alg == 0x0201:  # ECDSA SHA-256
        from cryptography.hazmat.primitives.asymmetric import ec
        chave_pub.verify(sig, dados, ec.ECDSA(hashes.SHA256()))
    else:
        raise ValueError(f"algoritmo {hex(alg)} não suportado no verificador")
    resultado["assinatura"] = "ok"

    digests, q = ler(dados, 0)
    certs, _ = ler(dados, q)
    d1, _ = ler(digests, 0)
    alg_d = struct.unpack_from("<I", d1, 0)[0]
    esperado, _ = ler(d1, 4)
    fim = bytearray(apk[eocd:])
    struct.pack_into("<I", fim, 16, inicio)
    if alg_d not in (0x0103, 0x0201, 0x0101):
        raise ValueError(f"resumo {hex(alg_d)} não suportado")
    calculado = _digest([apk[:inicio], apk[cd:eocd], bytes(fim)])
    if calculado != esperado:
        raise ValueError("resumo do conteúdo não bate (APK alterado depois de assinado)")
    resultado["resumo"] = "ok"
    c1, _ = ler(certs, 0)
    cert = x509.load_der_x509_certificate(c1)
    if cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != spki:
        raise ValueError("chave pública diferente do certificado")
    resultado["certificado"] = cert.subject.rfc4514_string()
    resultado["sha256_cert"] = hashlib.sha256(c1).hexdigest()
    return resultado


if __name__ == "__main__":
    import sys
    print(verificar(open(sys.argv[1], "rb").read()))
