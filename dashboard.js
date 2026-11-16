
// ==========================================
// 1. GEMELO DIGITAL 3D
// ==========================================

const ct = document.getElementById('canvas3d_container');

const s1 = new THREE.Scene();

const c1 = new THREE.PerspectiveCamera(
    45,
    ct.clientWidth / ct.clientHeight,
    0.1,
    100
);

const r1 = new THREE.WebGLRenderer({
    antialias: false,
    alpha: true
});

r1.setSize(ct.clientWidth, ct.clientHeight);

ct.appendChild(r1.domElement);


// ILUMINACIÓN

s1.add(
    new THREE.AmbientLight(0xffffff, 0.7)
);

const dl = new THREE.DirectionalLight(
    0x38bdf8,
    0.8
);

dl.position.set(5, 10, 7);

s1.add(dl);


// ESTRUCTURA DEL PUENTE

const puente = new THREE.Mesh(
    new THREE.BoxGeometry(10, 0.3, 2.5),
    new THREE.MeshLambertMaterial({
        color: 0x334155
    })
);

s1.add(puente);


// ROBOT

const rob = new THREE.Mesh(
    new THREE.BoxGeometry(0.8, 0.5, 0.8),
    new THREE.MeshLambertMaterial({
        color: 0x0284c7
    })
);

rob.position.set(-5, 0.4, 0);

s1.add(rob);


// CÁMARA 3D

c1.position.set(0, 5, 11);
c1.lookAt(0, 0, 0);


// MARCADORES DE FALLAS

function am3d(pp, t) {

    const x = (
        Math.min(Math.max(pp, 0.0), 1.0) * 10
    ) - 5;

    const es = new THREE.Mesh(
        new THREE.SphereGeometry(0.22, 8, 8),

        new THREE.MeshLambertMaterial({
            color: (
                t === "FISURA"
                ? 0xef4444
                : 0x10b981
            )
        })
    );

    es.position.set(x, 0.35, 0);

    s1.add(es);
}


// ANIMACIÓN 3D

function animar3D() {

    requestAnimationFrame(animar3D);

    r1.render(s1, c1);
}

animar3D();


// ==========================================
// 2. GRÁFICA DE FORMA MODAL
// ==========================================

const xs = Array.from(
    { length: 51 },
    (_, i) => i * 0.02
);

const yt = xs.map(
    x => Math.sin(Math.PI * x)
);


Plotly.newPlot(
    'plot_modal',

    [
        {
            x: xs,
            y: yt,
            mode: 'lines',
            name: 'Φ₁(x)',
            line: {
                dash: 'dot',
                color: '#64748b'
            }
        },

        {
            x: [0],
            y: [0],
            mode: 'markers',
            name: 'Robot',
            marker: {
                color: '#38bdf8',
                size: 9
            }
        },

        {
            x: [],
            y: [],
            mode: 'markers',
            name: 'Fisuras',
            marker: {
                color: '#ef4444',
                size: 10,
                symbol: 'x'
            }
        },

        {
            x: [],
            y: [],
            mode: 'markers',
            name: 'Corrosión',
            marker: {
                color: '#10b981',
                size: 10,
                symbol: 'x'
            }
        }
    ],

    {
        margin: {
            l: 30,
            r: 10,
            t: 10,
            b: 25
        },

        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',

        legend: {
            orientation: 'h',
            y: 1.15,
            font: {
                color: '#94a3b8',
                size: 9
            }
        },

        xaxis: {
            range: [0, 1.0],
            gridcolor: '#1e293b',
            color: '#94a3b8'
        },

        yaxis: {
            range: [-0.2, 1.2],
            gridcolor: '#1e293b',
            color: '#94a3b8'
        }
    },

    {
        responsive: true
    }
);


// ==========================================
// 3. GRÁFICA DE TELEMETRÍA ADXL345
// ==========================================

Plotly.newPlot(
    'plot_hilbert',

    [
        {
            x: [],
            y: [],
            mode: 'lines',
            name: 'Acel Z',
            line: {
                color: '#64748b',
                width: 1
            }
        },

        {
            x: [],
            y: [],
            mode: 'lines',
            name: 'A(t)',
            line: {
                color: '#f59e0b',
                width: 1.5
            }
        },

        {
            x: [],
            y: [],
            mode: 'lines',
            name: 'ω(t)',
            line: {
                color: '#c084fc',
                width: 1.5
            }
        }
    ],

    {
        margin: {
            l: 30,
            r: 10,
            t: 10,
            b: 25
        },

        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',

        legend: {
            orientation: 'h',
            y: 1.15,
            font: {
                color: '#94a3b8',
                size: 9
            }
        },

        xaxis: {
            gridcolor: '#1e293b',
            color: '#94a3b8'
        },

        yaxis: {
            gridcolor: '#1e293b',
            color: '#94a3b8'
        }
    },

    {
        responsive: true
    }
);


// ==========================================
// 4. CONTROL DE SENTIDO DEL ROBOT
// ==========================================

let cf = 0;


function setSentido(s) {

    fetch('/api/sentido', {

        method: 'POST',

        headers: {
            'Content-Type': 'application/json'
        },

        body: JSON.stringify({
            sentido: s
        })

    }).then(() => {

        document
            .getElementById('btn_ida')
            .classList.toggle('active', s === 'IDA');

        document
            .getElementById('btn_regreso')
            .classList.toggle('active', s === 'REGRESO');

    });

}


// ==========================================
// 5. ACTUALIZACIÓN DE TELEMETRÍA
// ==========================================

function act() {

    document.getElementById(
        'reloj_sistema'
    ).innerText = new Date().toLocaleTimeString();


    fetch('/api/telemetria')

        .then(r => r.json())

        .then(d => {

            // ----------------------------------
            // DATOS DE ODOMETRÍA
            // ----------------------------------

            document.getElementById(
                'sentido_tag'
            ).innerText =
                d.odometria.sentido +
                (d.odometria.bloqueado ? ' (FIN)' : '');


            document.getElementById(
                'dist_total'
            ).innerText =
                d.odometria.distancia_total_m.toFixed(3) + 'm';


            document.getElementById(
                'pos_puente'
            ).innerText =
                d.odometria.posicion_puente_m.toFixed(3) + 'm';


            document.getElementById(
                'vel'
            ).innerText =
                d.odometria.velocidad_ms.toFixed(2) + ' m/s';


            // ----------------------------------
            // MOVIMIENTO DEL ROBOT 3D
            // ----------------------------------

            rob.position.x = (
                Math.min(
                    Math.max(d.odometria.posicion_puente_m, 0.0),
                    1.0
                ) * 10
            ) - 5;


            // ----------------------------------
            // REGISTRO DE FALLAS 3D
            // ----------------------------------

            if (d.fallas.length > cf) {

                for (let i = cf; i < d.fallas.length; i++) {

                    am3d(
                        d.fallas[i].pos_puente_m,
                        d.fallas[i].tipo
                    );

                }

                cf = d.fallas.length;

            }


            // ----------------------------------
            // GRÁFICA HILBERT
            // ----------------------------------

            Plotly.update(

                'plot_hilbert',

                {
                    x: [
                        d.hilbert.t,
                        d.hilbert.t,
                        d.hilbert.t
                    ],

                    y: [
                        d.hilbert.raw,
                        d.hilbert.envolvente,
                        d.hilbert.frecuencia
                    ]
                }

            );


            // ----------------------------------
            // GRÁFICA MODAL
            // ----------------------------------

            const my = Math.sin(
                Math.PI *
                Math.min(d.odometria.posicion_puente_m, 1.0)
            );


            Plotly.update(

                'plot_modal',

                {
                    x: [
                        xs,

                        [d.odometria.posicion_puente_m],

                        d.fallas
                            .filter(f => f.tipo === "FISURA")
                            .map(f => f.pos_puente_m),

                        d.fallas
                            .filter(f => f.tipo === "CORROSION")
                            .map(f => f.pos_puente_m)
                    ],

                    y: [
                        yt,

                        [my],

                        d.fallas
                            .filter(f => f.tipo === "FISURA")
                            .map(f => Math.sin(Math.PI * f.pos_puente_m)),

                        d.fallas
                            .filter(f => f.tipo === "CORROSION")
                            .map(f => Math.sin(Math.PI * f.pos_puente_m))
                    ]

                },

                {},

                [0, 1, 2, 3]

            );


            // ----------------------------------
            // TABLA DE FALLAS
            // ----------------------------------

            document.getElementById(
                'count_fallas'
            ).innerText = `${d.fallas.length} Eventos`;


            if (d.fallas.length > 0) {

                document.getElementById(
                    'tabla_fallas'
                ).innerHTML = d.fallas.map(f => `

                    <tr>

                        <td>${f.hora}</td>

                        <td style="color:#38bdf8;">
                            ${f.sentido}
                        </td>

                        <td>
                            <b>X=${f.pos_puente_m.toFixed(2)}m</b>
                        </td>

                        <td class="${
                            f.tipo === 'FISURA'
                            ? 'tag-falla-red'
                            : 'tag-falla-green'
                        }">
                            ${f.tipo}
                        </td>

                        <td>${f.acel_z}</td>

                        <td>${f.frec_hz}</td>

                        <td style="font-size:0.7rem;color:#94a3b8;">

                            ${
                                f.lat
                                ? f.lat.toFixed(4) + '<br>' + f.lon.toFixed(4)
                                : '<span style="color:#ef4444">N/A</span>'
                            }

                        </td>

                        <td>

                            <u
                                style="cursor:pointer;color:var(--accent-amber);"

                                onclick="vf(
                                    '${f.foto}',
                                    '${f.pos_puente_m}',
                                    '${f.tipo}',
                                    '${f.lat}',
                                    '${f.lon}'
                                )">

                                Ver

                            </u>

                        </td>

                    </tr>

                `).join('');


                // ----------------------------------
                // ALERTAS
                // ----------------------------------

                const u = d.fallas[d.fallas.length - 1];

                document.getElementById(
                    'alert_box'
                ).style.borderLeft =
                    u.tipo === "FISURA"
                    ? '3px solid #ef4444'
                    : '3px solid #10b981';


                document.getElementById(
                    'alert_text'
                ).innerHTML = `
                    ⚠️ <b>${u.tipo}</b>:
                    Puente X =
                    <b>${u.pos_puente_m.toFixed(3)}m</b>
                    | Vib: ${u.acel_z} m/s²
                `;

            }

        })

        .catch(error => {

            console.error(
                'Error al obtener telemetría:',
                error
            );

        });

}


// ==========================================
// 6. ACTUALIZACIÓN AUTOMÁTICA
// ==========================================

setInterval(act, 1500);


// ==========================================
// 7. VISUALIZACIÓN DE FOTOGRAFÍAS
// ==========================================

function vf(r, p, t, l, lo) {

    if (!r) return;

    document.getElementById(
        'modal_img'
    ).src = r;


    document.getElementById(
        'modal_caption'
    ).innerHTML = `

        <b style="color:#38bdf8;">
            [${t}]
        </b>

        X=${p}m |

        GPS:

        ${
            l && l !== 'null'
            ? parseFloat(l).toFixed(5) +
              ', ' +
              parseFloat(lo).toFixed(5)
            : 'Buscando...'
        }

    `;


    document.getElementById(
        'modal_foto'
    ).style.display = 'flex';

}
