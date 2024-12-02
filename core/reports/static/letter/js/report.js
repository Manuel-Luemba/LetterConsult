// var date_now = new moment().format('YYYY-MM-DD');
// var date_30_days_ago = moment().subtract(30, 'days').format('YYYY-MM-DD');
// var date_range = null;
//
// function generate_report() {
//     var param = {
//         'action': 'search_report',
//         start_date: $('#start_date').val(),
//         end_date: $('#end_date').val(),
//         department: $('#department').val(),
//         status: $('#status').val()
//
//     };
//
//     // if (date_range !== null) {
//     //     param['start_date'] = date_range.startDate.format('YYYY-MM-DD');
//     //     param['end_date'] = date_range.endDate.format('YYYY-MM-DD');
//     // }
//
//     $('#data').DataTable({
//         responsive: true,
//         autoWidth: false,
//         destroy: true,
//         deferRender: true,
//         ajax: {
//             url: window.location.pathname,
//             type: 'POST',
//             data: param,
//             dataSrc: ""
//         },
//         columns: [
//             {"data": "id"},
//             {"data": "reference_code"},
//             {"data": "user_created"},
//             {"data": "department_name"},
//             {"data": "date_created"},
//             {"data": "status"},
//         ],
//         order: [[0, 'desc']],
//         columnDefs: [
//             {
//                 targets: [-1],
//                 class: 'text-center',
//                 orderable: false,
//                 render: function (data, type, row) {
//                     var html = '';
//                     if (row.status === 'reject') {
//                         html += '<span class="badge badge-danger">' + row.status_desc + '</span>';
//                     } else if (row.status === 'approved') {
//                         html += '<span class="badge badge-primary">' + row.status_desc + '</span>';
//                     } else if (row.status === 'sent') {
//                         html += '<span class="badge badge-success">' + row.status_desc + '</span>';
//                     } else {
//                         html += '<span class="badge badge-warning">' + row.status_desc + '</span>';
//                     }
//                     return html;
//                 }
//             },
//         ],
//         initComplete: function (settings, json) {
//         }
//     });
// }
//
// $(function () {
//     $('input[name="date_range"]').daterangepicker({
//         locale: {
//             "format": 'YYYY-MM-DD',
//             "separator": ' - ',
//             "applyLabel": '<i class="fas fa-chart-pie"></i> Confirmar',
//             "cancelLabel": '<i class="fas fa-times"></i> Cancelar',
//             "daysOfWeek": [
//                 "Dom",
//                 "Seg",
//                 "Ter",
//                 "Qua",
//                 "Qui",
//                 "Sex",
//                 "Sab"
//             ],
//             "monthNames": [
//                 "Jan",
//                 "Fev",
//                 "Mar",
//                 "Abr",
//                 "Mai",
//                 "Jun",
//                 "Jul",
//                 "Ago",
//                 "Set",
//                 "Out",
//                 "Nov",
//                 "Dez"
//             ],
//             "firstDay": 0
//         }
//     })
//     // .on('apply.daterangepicker', function (ev, picker) {
//     //     date_range = picker;
//     //     console.log( date_30_days_ago, 'mndd');
//     //     generate_report();
//     //  })//.on('apply.daterangepicker', function (ev, picker) {
//     //     console.log( date_30_days_ago, 'mndd');
//     //     // $(this).data('daterangepicker').setStartDate(date_30_days_ago);
//     //     // $(this).data('daterangepicker').setEndDate(date_now);
//     //     // date_range = picker;
//     //     // generate_report();
//     // });
//     generate_report();
// })
//
// $(document).ready(function () {
//     $('#filter-form').on('submit', function (e) {
//         console.log('xxxxx')
//         e.preventDefault();
//
//         $.ajax({
//             url: "{% url 'letter_report' %}",  // Defina a URL correta
//             type: 'GET',
//             data: $(this).serialize(),  // Serializa os dados do formulário
//             success: function (response) {
//                 $('#letter-list').html(response);  // Atualiza a lista de cartas
//             },
//             error: function () {
//                 alert('Erro ao carregar as cartas.');
//             }
//         });
//     });
// });


<!-- Código JavaScript -->

$(document).ready(function () {
var date_now = new moment().format('YYYY-MM-DD');
    $('#start_date').datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        //date: inicio.value,
        locale: 'pt',
        showButtonPanel: true,
        showTodayButton: true,
        keepOn: true,

    });

    $('#end_date').datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        //date: inicio.value,
        locale: 'pt',
        showButtonPanel: true,
        showTodayButton: true,
        keepOn: true,

    });

    // Função para inicializar o DataTable com os filtros aplicados
    function loadDataTable(param) {
        $('#data').DataTable({
            responsive: true,
            autoWidth: false,
            destroy: true,  // Permite recriar a tabela com novos dados
            deferRender: true,
            ajax: {
                url: window.location.pathname,  // URL para onde o AJAX vai enviar os dados
                type: 'POST',
                data: param,  // Envia os parâmetros de filtro
                dataSrc: ""  // A resposta virá como um array de objetos JSON
            },
            order: false,
            paging: false,
            ordering: false,
            info: false,
            searching: false,
            dom: 'Bfrtip',
            buttons: [
                {
                    extend: 'excelHtml5',
                    text: 'Descargar Excel <i class="fas fa-file-excel"></i>',
                    titleAttr: 'Excel',
                    className: 'btn btn-success btn-flat btn-xs'
                },
                {
                    extend: 'pdfHtml5',
                    text: 'Descargar Pdf <i class="fas fa-file-pdf"></i>',
                    titleAttr: 'PDF',
                    className: 'btn btn-danger btn-flat btn-xs',
                    download: 'open',
                    orientation: 'landscape',
                    pageSize: 'LEGAL',
                    customize: function (doc) {
                         var imgBase64 = 'data:image/png;base64,...';
                        doc.styles = {
                            header: {
                                fontSize: 18,
                                bold: true,
                                alignment: 'center'
                            },
                            subheader: {
                                fontSize: 13,
                                bold: true
                            },
                            quote: {
                                italics: true
                            },
                            small: {
                                fontSize: 8
                            },
                            tableHeader: {
                                bold: true,
                                fontSize: 11,
                                color: 'white',
                                fillColor: '#2d4154',
                                alignment: 'center'
                            }
                        };
                        doc.content[1].table.widths = ['5%', '20%', '15%', '15%', '15%', '15%'];
                        doc.content[1].margin = [0, 35, 0, 0];
                        doc.content[1].layout = {};
                        doc['footer'] = (function (page, pages) {
                            return {
                                columns: [
                                    {
                                        alignment: 'left',
                                        text: ['Data de criação: ', {text: date_now}]
                                    },
                                    {
                                        alignment: 'right',
                                        text: ['página ', {text: page.toString()}, ' de ', {text: pages.toString()}]
                                    }
                                ],
                                margin: 20
                            }
                        });

                    }
                }
            ],
            columns: [
                {"data": "reference_code"},
                {"data": "user_created"},
                {"data": "department_name"},
                {"data": "entity"},
                {"data": "city"},
                {"data": "date_created"},
                {"data": "status"},
            ],
            // order: [[0, 'desc']],  // Ordena pela coluna ID em ordem decrescente
            columnDefs: [
                {
                    targets: [-1],  // Define a coluna de status como a última
                    class: 'text-center',
                    orderable: false,
                    render: function (data, type, row) {
                        var html = '';
                        if (row.status === 'rejected') {
                            html += '<span class="badge badge-danger">' + row.status_desc + '</span>';
                        } else if (row.status === 'approved') {
                            html += '<span class="badge badge-primary">' + row.status_desc + '</span>';
                        } else if (row.status === 'sent') {
                            html += '<span class="badge badge-success">' + row.status_desc + '</span>';
                        } else {
                            html += '<span class="badge badge-warning">' + row.status_desc + '</span>';
                        }
                        return html;
                    }
                }
            ],
            initComplete: function (settings, json) {
                // Ação ao completar o carregamento dos dados (se necessário)
            }
        });
    }

    // Carrega o DataTable inicialmente sem filtros
    loadDataTable({
        'action': 'search_report',
        start_date: '',
        end_date: '',
        department: '',
        entity: '',
        status: ''
    });

    // Evento de submit do formulário de filtros
    $('#filter-form').on('submit', function (e) {
        e.preventDefault();

        // Cria um objeto com os valores dos filtros
        var param = {
            'action': 'search_report',
            start_date: $('#start_date').val(),
            end_date: $('#end_date').val(),
            department: $('#department').val(),
            entity: $('#entity').val(),
            status: $('#status').val()
        };

        // Recarrega a tabela com os filtros aplicados
        console.log('inicio')
        loadDataTable(param);
        console.log('final')
    });

});


