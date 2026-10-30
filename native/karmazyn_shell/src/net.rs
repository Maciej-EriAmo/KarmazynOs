//! Sieć PID 1: `lo` i interfejs z adresem statycznym, bez demonów.
//!
//! Konfiguracja z linii poleceń jądra (trafia do środowiska procesu 1):
//! `KARMAZYN_IP=<adres>/<prefiks>`, `KARMAZYN_GW=<brama>`,
//! `KARMAZYN_NET_IF=<interfejs>` (domyślnie `eth0`). Bez `KARMAZYN_IP`
//! sieć zostaje wyłączona — nie zgadujemy adresów.
//!
//! Sterownik (np. `virtio_net`) ładuje `disk::prepare` razem z innymi
//! modułami z `/lib/modules`.

use std::net::Ipv4Addr;

/// Adres i maska z `a.b.c.d/nn`.
pub fn parse_cidr(s: &str) -> Result<(Ipv4Addr, Ipv4Addr, u8), String> {
    let (ip, prefix) = s.split_once('/').unwrap_or((s, "24"));
    let ip: Ipv4Addr = ip.trim().parse().map_err(|e| format!("KARMAZYN_IP {s:?}: {e}"))?;
    let prefix: u8 = prefix.trim().parse().map_err(|e| format!("KARMAZYN_IP {s:?}: {e}"))?;
    if prefix > 32 {
        return Err(format!("KARMAZYN_IP {s:?}: prefiks > 32"));
    }
    let mask = if prefix == 0 { 0 } else { u32::MAX << (32 - prefix) };
    Ok((ip, Ipv4Addr::from(mask), prefix))
}

/// Ustawienia z env. `None` = sieć wyłączona.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub struct Config {
    pub iface: String,
    pub ip: Ipv4Addr,
    pub mask: Ipv4Addr,
    pub prefix: u8,
    pub gw: Option<Ipv4Addr>,
}

pub fn config_from_env() -> Result<Option<Config>, String> {
    let get = |k: &str| std::env::var(k).ok().map(|v| v.trim().to_string()).filter(|v| !v.is_empty());
    let Some(ip) = get("KARMAZYN_IP") else {
        return Ok(None);
    };
    let (ip, mask, prefix) = parse_cidr(&ip)?;
    let gw = match get("KARMAZYN_GW") {
        Some(g) => Some(g.parse().map_err(|e| format!("KARMAZYN_GW {g:?}: {e}"))?),
        None => None,
    };
    Ok(Some(Config {
        iface: get("KARMAZYN_NET_IF").unwrap_or_else(|| "eth0".into()),
        ip,
        mask,
        prefix,
        gw,
    }))
}

#[cfg(target_os = "linux")]
mod sys {
    use std::io;
    use std::net::Ipv4Addr;

    const IFNAMSIZ: usize = 16;

    /// `struct ifreq` jako bajty: nazwa (16 B) + unia (24 B).
    fn ifreq(name: &str) -> io::Result<[u8; 40]> {
        if name.len() >= IFNAMSIZ {
            return Err(io::Error::other(format!("{name}: za długa nazwa interfejsu")));
        }
        let mut r = [0u8; 40];
        r[..name.len()].copy_from_slice(name.as_bytes());
        Ok(r)
    }

    fn put_sockaddr(buf: &mut [u8], ip: Ipv4Addr) {
        // sockaddr_in: family (natywnie), port (0), adres (sieciowo)
        buf[..2].copy_from_slice(&(libc::AF_INET as u16).to_ne_bytes());
        buf[2..4].copy_from_slice(&[0, 0]);
        buf[4..8].copy_from_slice(&ip.octets());
    }

    struct Sock(i32);

    impl Drop for Sock {
        fn drop(&mut self) {
            // SAFETY: deskryptor z socket()
            unsafe { libc::close(self.0) };
        }
    }

    fn sock() -> io::Result<Sock> {
        // SAFETY: zwykłe wywołanie systemowe
        let fd = unsafe { libc::socket(libc::AF_INET, libc::SOCK_DGRAM, 0) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Sock(fd))
    }

    fn ioctl(s: &Sock, req: libc::c_ulong, arg: *mut u8, what: &str) -> io::Result<()> {
        // SAFETY: arg wskazuje na bufor o rozmiarze oczekiwanym przez żądanie
        let rc = unsafe { libc::ioctl(s.0, req as _, arg) };
        if rc < 0 {
            let e = io::Error::last_os_error();
            return Err(io::Error::new(e.kind(), format!("{what}: {e}")));
        }
        Ok(())
    }

    pub fn exists(name: &str) -> bool {
        let (Ok(s), Ok(mut r)) = (sock(), ifreq(name)) else {
            return false;
        };
        ioctl(&s, libc::SIOCGIFFLAGS as _, r.as_mut_ptr(), "SIOCGIFFLAGS").is_ok()
    }

    pub fn up(name: &str) -> io::Result<()> {
        let s = sock()?;
        let mut r = ifreq(name)?;
        ioctl(&s, libc::SIOCGIFFLAGS as _, r.as_mut_ptr(), &format!("{name} flags"))?;
        let flags = i16::from_ne_bytes([r[16], r[17]]) | (libc::IFF_UP | libc::IFF_RUNNING) as i16;
        r[16..18].copy_from_slice(&flags.to_ne_bytes());
        ioctl(&s, libc::SIOCSIFFLAGS as _, r.as_mut_ptr(), &format!("{name} up"))
    }

    pub fn set_addr(name: &str, ip: Ipv4Addr, mask: Ipv4Addr) -> io::Result<()> {
        let s = sock()?;
        let mut r = ifreq(name)?;
        put_sockaddr(&mut r[16..], ip);
        ioctl(&s, libc::SIOCSIFADDR as _, r.as_mut_ptr(), &format!("{name} adres"))?;
        let mut r = ifreq(name)?;
        put_sockaddr(&mut r[16..], mask);
        ioctl(&s, libc::SIOCSIFNETMASK as _, r.as_mut_ptr(), &format!("{name} maska"))
    }

    pub fn default_route(gw: Ipv4Addr) -> io::Result<()> {
        let s = sock()?;
        // SAFETY: rtentry z samymi zerami jest poprawny; wypełniamy pola niżej
        let mut rt: libc::rtentry = unsafe { std::mem::zeroed() };
        let sa = |ip: Ipv4Addr| {
            let mut b = [0u8; 16];
            put_sockaddr(&mut b, ip);
            // SAFETY: sockaddr ma 16 B jak bufor
            unsafe { std::mem::transmute::<[u8; 16], libc::sockaddr>(b) }
        };
        rt.rt_dst = sa(Ipv4Addr::UNSPECIFIED);
        rt.rt_genmask = sa(Ipv4Addr::UNSPECIFIED);
        rt.rt_gateway = sa(gw);
        rt.rt_flags = (libc::RTF_UP | libc::RTF_GATEWAY) as _;
        let p = &mut rt as *mut libc::rtentry as *mut u8;
        match ioctl(&s, libc::SIOCADDRT as _, p, "trasa domyślna") {
            // trasa już jest (ponowne `net up`)
            Err(e) if e.raw_os_error() == Some(libc::EEXIST) => Ok(()),
            r => r,
        }
    }
}

/// Podnosi `lo` i interfejs z `cfg`. Czeka do 3 s na pojawienie się
/// interfejsu (sterownik ładuje się chwilę). Zwraca opis do linii startowej.
#[cfg(target_os = "linux")]
pub fn bring_up(cfg: &Config) -> Result<String, String> {
    use std::time::{Duration, Instant};
    let _ = sys::set_addr("lo", Ipv4Addr::LOCALHOST, Ipv4Addr::new(255, 0, 0, 0));
    let _ = sys::up("lo");
    let end = Instant::now() + Duration::from_secs(3);
    while !sys::exists(&cfg.iface) {
        if Instant::now() > end {
            return Err(format!("{}: brak interfejsu (sterownik?)", cfg.iface));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    sys::set_addr(&cfg.iface, cfg.ip, cfg.mask).map_err(|e| e.to_string())?;
    sys::up(&cfg.iface).map_err(|e| e.to_string())?;
    let mut line = format!("{} {}/{}", cfg.iface, cfg.ip, cfg.prefix);
    if let Some(gw) = cfg.gw {
        sys::default_route(gw).map_err(|e| e.to_string())?;
        line.push_str(&format!(" gw {gw}"));
    }
    Ok(line)
}

#[cfg(not(target_os = "linux"))]
pub fn bring_up(_cfg: &Config) -> Result<String, String> {
    Err("sieć z shella tylko na Linuksie (płyta)".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cidr_parsing() {
        let (ip, mask, p) = parse_cidr("10.0.2.15/24").unwrap();
        assert_eq!((ip, mask, p), (Ipv4Addr::new(10, 0, 2, 15), Ipv4Addr::new(255, 255, 255, 0), 24));
        assert_eq!(parse_cidr("192.168.1.7/20").unwrap().1, Ipv4Addr::new(255, 255, 240, 0));
        assert_eq!(parse_cidr("10.0.0.1").unwrap().2, 24);
        assert!(parse_cidr("10.0.0.1/33").is_err());
        assert!(parse_cidr("nie-ip/24").is_err());
    }
}
