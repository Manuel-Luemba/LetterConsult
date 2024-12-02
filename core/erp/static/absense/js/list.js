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
                        if(row.status == 'CANCELADO'){
                         html += '<span class="badge badge-danger">' + row.status + '</span>';
                        } else if (row.status == 'APROVADO'){
                         html += '<span class="badge badge-success">' + row.status + '</span>';
                        } else{
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
                   var dot = document.getElementById('manager').value
                   console.log(dot, 'dot')
                    var buttons = "";
                   if(dot == "NÃO"){

                        buttons = '<a href="/erp/absence/update/' + row.id + '/" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';

                    }else {
                         buttons = '<a href="/erp/absence/aprove/manager/' + row.id + '/" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';

                    }

                    if(row.status =="APROVADO" && dot == "NÃO"){

                    }

                    else {
                    buttons += '<a href="/erp/absence/delete/' + row.id + '/" type="button" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash-alt"></i></a>';

                    }

                  if(row.status =="APROVADO"){
                  console.log("aprovado")
//                     buttons += '<a rel="details" class="btn btn-success btn-xs btn-flat"><i class="fas fa-search"></i></a> ';
                     buttons += '<a href="/erp/absence/view/pdf/'+row.id+'/" target="_blank" class="btn btn-info btn-xs btn-flat"><i class="fas fa-file-pdf"></i></a> ';
                    }

                    return buttons;
                }
            },
        ],
        initComplete: function (settings, json) {

        }
    });

function mi_list(manager){
if(manager == 'SIM'){
    console.log(manager)
}
else {
    console.log("NÃO QUERO MANAGER", manager)
}

}
});
