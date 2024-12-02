$(function () {
    $('#data').DataTable({
        responsive: true,
        autoWidth: false,
        destroy: true,
        deferRender: true,
        ajax: {
            url: window.location.pathname,
            type: 'POST',
            data: {
                'action': 'searchdata'
            },
            dataSrc: ""
        },
        columns: [
            {"data": "id"},
            {"data": "type"},
            {"data": "reason"},
            {"data": "user_created"},
            {"data": "start_date"},
            {"data": "end_date"},
            {"data": "days_absence"},
            {"data": "status"},
            {"data": "status"},

        ],

        columnDefs: [
            {
                targets: [-2],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    var html = '';
                    if (row.status == 'CANCELADO') {
                        html += '<span class="badge badge-danger">' + row.status + '</span>';
                    } else if (row.status == 'APROVADO') {
                        html += '<span class="badge badge-success">' + row.status + '</span>';
                    } else {
                        html += '<span class="badge badge-warning">' + row.status + '</span>';
                    }


                    return html;
                }
            },

            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    console.log(data, 'cc');
                    var buttons = '<a href="/erp/absence/aprove/' + row.id + '/" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                    return buttons;
                }
            },
        ],
        initComplete: function (settings, json) {

        }
    });
});