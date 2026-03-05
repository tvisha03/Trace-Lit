"""Diagnose PDF extraction for the corrupted uploaded file."""
import pymupdf
import zlib

path = "data/uploads/f5710953-5274-4e5a-9121-1ca56fa03d32/fl_paper.pdf"
doc = pymupdf.open(path)

print(f"xref length: {doc.xref_length()}")

page = doc[0]
print(f"Page 0 xref: {page.xref}")

contents = page.get_contents()
print(f"Page 0 content streams: {contents}")

for xref_num in contents:
    try:
        stream_raw = doc.xref_stream_raw(xref_num)
        print(f"  xref {xref_num}: raw stream {len(stream_raw)} bytes, first 20: {stream_raw[:20]}")

        # Try manual zlib decompression with different approaches
        for wbits in [15, -15, 31, 47]:
            try:
                decompressed = zlib.decompress(stream_raw, wbits)
                text = decompressed.decode("latin-1", errors="replace")[:200]
                print(f"  Manual zlib (wbits={wbits}): {len(decompressed)} bytes => {repr(text)}")
                break
            except zlib.error as e:
                pass

        # Try the decoded stream via pymupdf
        try:
            stream_decoded = doc.xref_stream(xref_num)
            if stream_decoded:
                print(f"  pymupdf decoded: {len(stream_decoded)} bytes")
        except Exception as e:
            print(f"  pymupdf decode error: {e}")

    except Exception as e:
        print(f"  xref {xref_num}: error: {e}")

# Check if pdfminer can handle it
print("\n=== Trying pdfminer.six ===")
try:
    from pdfminer.high_level import extract_text
    text = extract_text(path, maxpages=2)
    print(f"pdfminer extracted {len(text)} chars")
    if text.strip():
        print(f"First 300: {repr(text[:300])}")
    else:
        print("pdfminer also empty")
except ImportError:
    print("pdfminer not installed")
except Exception as e:
    print(f"pdfminer error: {e}")

doc.close()
