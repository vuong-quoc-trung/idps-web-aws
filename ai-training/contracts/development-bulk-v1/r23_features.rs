//! Numeric projection of the bounded, privacy-screened R23 class sketch.
use std::io::{self, BufRead};

const SYMBOLS: &[u8] = b"/=?&-_.:+*{}[]();!%,~";
const BINS: usize = 128;

fn describe(value: &[u8], split: u8) -> [u8; 12] {
    let items: Vec<_> = if value.is_empty() {
        Vec::new()
    } else {
        value.split(|&b| b == split).map(<[u8]>::len).collect()
    };
    let count = |symbol| value.iter().filter(|&&b| b == symbol).count();
    let n = [
        usize::from(!value.is_empty()),
        items.len(),
        value.len(),
        items.iter().copied().max().unwrap_or(0),
        items.first().copied().unwrap_or(0),
        items.last().copied().unwrap_or(0),
        count(b'0'),
        count(b'A'),
        count(b'a'),
        value.iter().filter(|b| SYMBOLS.contains(b)).count(),
        count(b'?'),
        value.windows(2).filter(|pair| pair[0] != pair[1]).count(),
    ];
    n.map(|x| x.min(31) as u8)
}

fn project(path: &[u8], query: &[u8]) -> [u8; 24 + BINS] {
    let mut out = [0; 24 + BINS];
    out[..12].copy_from_slice(&describe(path, b'/'));
    out[12..24].copy_from_slice(&describe(query, b'&'));
    for (lane, value) in [path, query].iter().enumerate() {
        if value.is_empty() {
            continue;
        }
        let mut framed = Vec::with_capacity(value.len() + 2);
        framed.push(b'^');
        framed.extend_from_slice(value);
        framed.push(b'$');
        for width in [2, 3] {
            for chunk in framed.windows(width) {
                let code = chunk
                    .iter()
                    .fold(0x811c_9dc5 ^ (17 * lane + width) as u32, |h, &byte| {
                        (h ^ u32::from(byte)).wrapping_mul(0x0100_0193)
                    });
                let cell = &mut out[24 + (code as usize & (BINS - 1))];
                *cell = (*cell + 1).min(15);
            }
        }
    }
    out
}

fn main() -> io::Result<()> {
    for frame in io::stdin().lock().lines() {
        let frame = frame?;
        let (path, query) = frame
            .split_once('\t')
            .filter(|(path, query)| {
                [*path, *query].iter().all(|s| {
                    s.len() <= 512
                        && s.bytes()
                            .all(|b| SYMBOLS.contains(&b) || b"Aa0?".contains(&b))
                })
            })
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Invalid class sketch"))?;
        for byte in project(path.as_bytes(), query.as_bytes()) {
            print!("{byte:02x}");
        }
        println!();
    }
    Ok(())
}
