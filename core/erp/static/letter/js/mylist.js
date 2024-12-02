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
            {"data": "reference_code"},
            {"data": "title"},
            {"data": "date_sent"},
            {"data": "user_created"},
            {"data": "status"},
            {"data": "title"},
        ],
        order: [[0, 'desc']],
        columnDefs: [
            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    var buttons = '';
                    if (row.status !== 'approved' && row.status !== 'sent') {
                        buttons += '<a href="/erp/letter/approve/' + row.id + '/" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                    }
                    buttons += '<a href="/erp/letter/detail/' + row.id + '/" type="button" class="btn btn-info btn-xs btn-flat"><i class="fas fa-eye"></i></a> ';
                    //buttons += '<a href="/erp/letter/delete/' + row.id + '/" type="button" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash-alt"></i></a>';

                                 if (row.status === 'approved') {
                                       buttons += '<a href="/erp/letter/approve/' + row.id + '/" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                        buttons += '<a href="/erp/letter/download/' + row.id + '/" class="btn btn-primary btn-xs btn-flat"><i class="fa fa-cloud-download"></i></a> ';

                    }
                      if ( row.status === 'sent') {
                           buttons += '<a href="/erp/letter/download/' + row.id + '/" class="btn btn-primary btn-xs btn-flat"><i class="fa fa-cloud-download"></i></a> ';
                        buttons += '<a href="/erp/letter/downloadprotocol/' + row.id + '/" class="btn btn-success btn-xs btn-flat"><i class="fa fa-cloud-download"></i></a> ';

                    }

                    return buttons;
                }
            },
            {
                targets: [-2],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                   var html = '';
                    if (row.status == 'rejected') {
                        html += '<span class="badge badge-danger">' + row.status_desc + '</span>';
                    } else if (row.status == 'approved') {
                        html += '<span class="badge badge-primary">' + row.status_desc + '</span>';
                    }
                    else if (row.status == 'sent') {
                        html += '<span class="badge badge-success">' + row.status_desc + '</span>';
                    }
                    else {
                        html += '<span class="badge badge-warning">' + row.status_desc + '</span>';
                    }
                    return html;
                }
            },
        ],
        initComplete: function (settings, json) {

        }
    });
})
;