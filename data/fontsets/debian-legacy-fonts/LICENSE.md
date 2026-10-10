# Licences of the fonts in `data/fontsets/debian-legacy-fonts/`

These fonts are copies of BDF fonts from Debian's console-setup 1.242~deb13u1, and they are
licensed in several different ways. Every file keeps the notice it was distributed with. The
table says which licence covers which files; the texts follow exactly as Debian's
`copyright.fonts` gives them, with the list of files in each group made from what this
directory actually holds.

Debian states that the console fonts built from them "are public domain by nature". That
does not change the licences of the source fonts listed here, which this project keeps.

| Files | Holders and licence |
|---|---|
| **Public domain: misc-fixed variants and the ETL fonts**<br>13 files: `7x14-IL2.bdf`, `7x14B-IL2.bdf`, `7x14c.bdf`, `8x13-IL2.bdf`, ... | Public domain. Donated by many people (see AUTHORS.md). The `-IL2` files are re-encodings by BIZNET Poland, Inc. ("Copyright (c) 1996 BIZNET Poland, Inc." in the files); the `c` files add the upper-half glyphs. |
| **Sony Corp.: 8x16**<br>`8x16-IL2.bdf`, `8x16c.bdf` | Copyright Sony Corp., BIZNET Poland, Inc. and Dmitry Yu. Bolkhovityanov; permissive licence. |
| **/efont/ The Electronic Font Open Laboratory**<br>`georgian14.bdf`, `h14.bdf`, `h14_b.bdf`, `h16.bdf`, `h16_b.bdf`, `h24.bdf`, `h24_b.bdf` | Copyright 2000-2001 /efont/; BSD-style licence. `georgian14.bdf` carries /efont/'s copyright notice in the file itself; Debian's list does not name it. |
| **GNU Unifont**<br>`unifont.bdf` | Copyright 1999-2002 Roman Czyborra, David Starner and others; freeware, with attribution. |
| **Courier (Adobe Systems, Digital Equipment Corporation)**<br>16 files: `100dpi-courB10-IL2.bdf`, `100dpi-courB10.bdf`, `100dpi-courR10-IL2.bdf`, `100dpi-courR10.bdf`, ... | Copyright Adobe Systems Incorporated and Digital Equipment Corporation, with the BIZNET Poland and Bolkhovityanov re-encodings; permissive licence. |
| **Lucida Typewriter (Sun Microsystems, AT&T, Bigelow & Holmes)**<br>26 files: `100dpi-lutBS08-IL2.bdf`, `100dpi-lutBS08.bdf`, `100dpi-lutBS10-IL2.bdf`, `100dpi-lutBS10.bdf`, ... | Copyright Sun Microsystems, Inc. and Bigelow & Holmes, with the BIZNET Poland and Bolkhovityanov re-encodings. The licence requires notices to appear with any use of the fonts; they are in the text below. These faces (`Lucid*`) are not built by default. |
| **Georgian (Gia Shervashidze)**<br>`georgian16.bdf` | Public domain (converted from the author's hex-format font). |
| **Fonts generated from console fonts, and the Goha fonts**<br>40 files: `Goha12.bdf`, `Goha14.bdf`, `Goha16.bdf`, `GohaClassic12.bdf`, ... | Public domain. The `legacy*-double.bdf` files are twofold pixel enlargements of the `legacy*.bdf` files of the same name. |

## Public domain: misc-fixed variants and the ETL fonts

Files: `7x14-IL2.bdf`, `7x14B-IL2.bdf`, `7x14c.bdf`, `8x13-IL2.bdf`, `8x13Bc.bdf`, `8x13c.bdf`, `9x15-IL2.bdf`, `9x15B-IL2.bdf`, `9x15Bc.bdf`, `9x15c.bdf`, `etl14-unicode.bdf`, `etl16-unicode.bdf`, `etl24-unicode.bdf`

```text
Public domain.  Donated (in unspecified order) by H. Kagotani
<kagotani@cs.titech.ac.jp>, BIZNET Poland, Inc., Dmitry
Yu. Bolkhovityanov <bolkhov@inp.nsk.su>, Thomas Bagli
<pyramid!pcsbst!tom@uunet.UU.NET>, PCS Computer Systeme - West
Germany, Takahashi N. <ntakahas@etl.go.jp>, Mark J. Reed
<mark_reed@sware.com>, P. Peterlin
<primoz.peterlin@biofiz.mf.uni-lj.si>, Mark Leisher
<mleisher@crl.nmsu.edu>, Roman Czyborra <czyborra@cs.tu-berlin.de>,
Kosta Kostis <kosta@live.robin.de> and others.
```

## Sony Corp.: 8x16

Files: `8x16-IL2.bdf`, `8x16c.bdf`

```text
Copyright 1987, 1988, 1989 by Sony Corp.
Copyright 1996 BIZNET Poland, Inc.
Copyright 2000 by Dmitry Yu. Bolkhovityanov, bolkhov@inp.nsk.su

Permission to use, copy, modify, and distribute this software and
its documentation for any purpose and without fee is hereby granted,
provided that the above copyright notices appear in all copies and
that both those copyright notices and this permission notice appear
in supporting documentation, and that the name of Sony Corp.
not be used in advertising or publicity pertaining to distribution
of the software without specific, written prior permission.  Sony
Corp. makes no representations about the suitability of this
software for any purpose.  It is provided "as is" without express or
implied warranty.

SONY DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS, IN NO EVENT SHALL SONY BE LIABLE FOR ANY
SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF
CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

## /efont/ The Electronic Font Open Laboratory

Files: `georgian14.bdf`, `h14.bdf`, `h14_b.bdf`, `h16.bdf`, `h16_b.bdf`, `h24.bdf`, `h24_b.bdf`

```text
Copyright © 2000-2001 /efont/ The Electronic Font Open Laboratory.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
3. Neither the name of the team nor the names of its contributors
   may be used to endorse or promote products derived from this font
   without specific prior written permission.

THIS FONT IS PROVIDED BY THE TEAM AND CONTRIBUTORS ``AS IS'' AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE TEAM OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS FONT, EVEN
IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## GNU Unifont

Files: `unifont.bdf`

```text
Copyright © 1999-2002 Roman Czyborra, David Starner and others

The following is taken from http://czyborra.com/

All of my works you find here are freeware. You may freely copy, use, quote,
modify or redistribute them as long as you properly attribute my contribution
and have given a quick thought about whether Roman might perhaps be interested
to read what you did with his stuff. Horizontal rules don't apply.
```

## Courier (Adobe Systems, Digital Equipment Corporation)

Files: `100dpi-courB10-IL2.bdf`, `100dpi-courB10.bdf`, `100dpi-courR10-IL2.bdf`, `100dpi-courR10.bdf`, `75dpi-courB12-IL2.bdf`, `75dpi-courB12.bdf`, `75dpi-courB12c.bdf`, `75dpi-courB14-IL2.bdf`, `75dpi-courB14.bdf`, `75dpi-courB14c.bdf`, `75dpi-courR12-IL2.bdf`, `75dpi-courR12.bdf`, `75dpi-courR12c.bdf`, `75dpi-courR14-IL2.bdf`, `75dpi-courR14.bdf`, `75dpi-courR14c.bdf`

```text
Copyright 1984-1989, 1994 Adobe Systems Incorporated.
Copyright 1988, 1994 Digital Equipment Corporation.
Copyright 1996 BIZNET Poland, Inc.
Copyright 2000 Dmitry Yu. Bolkhovityanov, bolkhov@inp.nsk.su

Permission to use, copy, modify, distribute and sell this software
and its documentation for any purpose and without fee is hereby
granted, provided that the above copyright notices appear in all
copies and that both those copyright notices and this permission
notice appear in supporting documentation, and that the names of
Adobe Systems and Digital Equipment Corporation not be used in
advertising or publicity pertaining to distribution of the software
without specific, written prior permission.  Adobe Systems and
Digital Equipment Corporation make no representations about the
suitability of this software for any purpose.  It is provided "as
is" without express or implied warranty.
```

## Lucida Typewriter (Sun Microsystems, AT&T, Bigelow & Holmes)

Files: `100dpi-lutBS08-IL2.bdf`, `100dpi-lutBS08.bdf`, `100dpi-lutBS10-IL2.bdf`, `100dpi-lutBS10.bdf`, `100dpi-lutBS14-IL2.bdf`, `100dpi-lutBS14.bdf`, `100dpi-lutBS19.bdf`, `100dpi-lutRS08-IL2.bdf`, `100dpi-lutRS08.bdf`, `100dpi-lutRS10-IL2.bdf`, `100dpi-lutRS10.bdf`, `100dpi-lutRS14-IL2.bdf`, `100dpi-lutRS14.bdf`, `100dpi-lutRS19.bdf`, `75dpi-lutBS12-IL2.bdf`, `75dpi-lutBS12.bdf`, `75dpi-lutBS12c.bdf`, `75dpi-lutBS14-IL2.bdf`, `75dpi-lutBS14.bdf`, `75dpi-lutBS14c.bdf`, `75dpi-lutRS12-IL2.bdf`, `75dpi-lutRS12.bdf`, `75dpi-lutRS12c.bdf`, `75dpi-lutRS14-IL2.bdf`, `75dpi-lutRS14.bdf`, `75dpi-lutRS14c.bdf`

```text
Copyright 1989 Sun Microsystems, Inc.
Copyright 1986, 1985 Bigelow & Holmes
Copyright 1996 BIZNET Poland, Inc.
Copyright 2000 Dmitry Yu. Bolkhovityanov, bolkhov@inp.nsk.su

NOTICE TO USER: The source code, including the glyphs or icons forming
a par of the OPEN LOOK TM Graphic User Interface, on this tape and in
these files is copyrighted under U.S. and international laws. Sun
Microsystems, Inc. of Mountain View, California owns the copyright and
has design patents pending on many of the icons. AT&T is the owner of
the OPEN LOOK trademark associated with the materials on this
tape. Users and possessors of this source code are hereby granted a
nonexclusive, royalty-free copyright and design patent license to use
this code in individual and commercial software. A royalty-free,
nonexclusive trademark license to refer to the code and output as
"OPEN LOOK" compatible is available from AT&T if, and only if, the
appearance of the icons or glyphs is not changed in any manner except
as absolutely necessary to accommodate the standard resolution of the
screen or other output device, the code and output is not changed
except as authorized herein, and the code and output is validated by
AT&T.

Bigelow & Holmes is the owner of the Lucida (R) trademark for the
fonts and bit-mapped images associated with the materials on this
tape. Users are granted a royalty-free, nonexclusive license to use
the trademark only to identify the fonts and bit-mapped images if, and
only if, the fonts and bit-mapped images are not modified in any way
by the user.

Any use of this source code must include, in the user documentation
and internal comments to the code, notices to the end user as follows:

Copyright © 1989 Sun Microsystems, Inc. Sun design patents pending
in the U.S. and foreign countries. OPEN LOOK is a trademark of
AT&T. Used by written permission of the owners.

Copyright © Bigelow & Holmes 1986, 1985. Lucida is a registered
trademark of Bigelow & Holmes. Permission to use the Lucida trademark
is hereby granted only in association with the images and fonts
described in this file.

SUN MICROSYSTEMS, INC., AT&T, AND BIGELOW & HOLMES MAKE NO
REPRESENTATIONS ABOUT THE SUITABILITY OF THIS SOURCE CODE FOR ANY
PURPOSE. IT IS PROVIDED "AS IS" WITHOUT EXPRESS OR IMPLIED WARRANTY OF
ANY KIND. SUN MICROSYSTEMS, INC., AT&T AND BIGELOW & HOLMES, SEVERALLY
AND INDIVIDUALLY, DISCLAIM ALL WARRANTIES WITH REGARD TO THIS SOURCE
CODE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
FOR A PARTICULAR PURPOSE. IN NO EVENT SHALL SUN MICROSYSTEMS, INC.,
AT&T OR BIGELOW & HOLMES BE LIABLE FOR ANY SPECIAL, INDIRECT,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF
CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOURCE CODE.
```

## Georgian (Gia Shervashidze)

Files: `georgian16.bdf`

```text
The author of this mini-font is Gia Shervashidze.  This font was
provided in hex format and converted automatically to bdf with hex2bdf
utility from the unifont suite.  This makes it public domain.
```

## Fonts generated from console fonts, and the Goha fonts

Files: `Goha12.bdf`, `Goha14.bdf`, `Goha16.bdf`, `GohaClassic12.bdf`, `GohaClassic14.bdf`, `GohaClassic16.bdf`, `legacy10a.bdf`, `legacy10b.bdf`, `legacy10d.bdf`, `legacy12a.bdf`, `legacy12c.bdf`, `legacy12d.bdf`, `legacy14a-double.bdf`, `legacy14a.bdf`, `legacy14b-double.bdf`, `legacy14b.bdf`, `legacy14c-double.bdf`, `legacy14c.bdf`, `legacy14e-double.bdf`, `legacy14e.bdf`, `legacy14f-double.bdf`, `legacy14f.bdf`, `legacy14g-double.bdf`, `legacy14g.bdf`, `legacy14h-double.bdf`, `legacy14h.bdf`, `legacy14i-double.bdf`, `legacy14i.bdf`, `legacy14k-double.bdf`, `legacy14k.bdf`, `legacy14l-double.bdf`, `legacy14l.bdf`, `legacy19a.bdf`, `legacy8a.bdf`, `legacy8b.bdf`, `legacy8c.bdf`, `legacy8d.bdf`, `legacy8e.bdf`, `legacy8f.bdf`, `legacy8i.bdf`

```text
These fonts were automatically generated from console fonts.  Because
of that they are public domain.  The Goha and GohaClassic fonts are
donated by Yitna Firdyiwek <ybf2u@virgina.edu> of GohaTibeb
Associates.
```

## Note on the `-IL2` fonts

```text
The *-IL2.bdf fonts were automaticaly reencoded from ISO 8859-2 to
ISO 10646-1 by the trbdf utility.
```
