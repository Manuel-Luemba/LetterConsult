$(function () {

    //alert('xxx');

    let txt_reference = $('#id_reference_code');

    var inicio1 = document.getElementById("id_reference_code");
    var inicio2 = document.getElementById("id_user_department");

   let txt_department = $('#id_user_department')
   //txt_department.prop("disabled", true);
   //txt_department.value=department;
   inicio2.value=department

   const initials = first_name.charAt(0) + last_name.charAt(0);

   const abbrev = abbreviation;
   const currentDate = new Date();
   const year = String(currentDate.getFullYear()).slice(-2);
   const month = String(currentDate.getMonth() + 1).padStart(2, '0');
   const day = String(currentDate.getDate()).padStart(2, '0');
   const formattedDate = `${year}-${month}-${day}`;

   console.log(formattedDate); // Saída: "24-08-20"
   console.log(abbreviation, 'abrev')
   console.log(counter, 'COUNTER')
   const contador = Number( Number(counter) +1);
   const reference = initials+'_'+abbrev+'_'+formattedDate+'_'+contador;


   //txt_reference.prop("disabled", true);
   //txt_reference.value=reference;
   inicio1.value=reference;


   // $('select[name="manager"]').select2({
   //       theme: "bootstrap4",
   //       language: 'pt-pt',
   //        allowClear: true,
   //       placeholder: 'Selecione o Chefe',
   //   });


//     // search clients
//    $('select[name="reason"]').select2({
//        theme: "bootstrap4",
//        language: 'pt-pt',
//        allowClear: true,
//        ajax: {
//            delay: 250,
//            type: 'POST',
//            url: '/erp/type/list/',
//            data: function (params) {
//                var queryParameters = {
//                    term: params.term,
//                    action: 'searchdata'
//                }
//                return queryParameters;
//            },
//            processResults: function (data) {
//            console.log(data)
//            console.log(window.location.pathname)
//                return {
//                    results: data
//                };
//            },
//        },
//        placeholder: 'Escreve uma Descrição',
//        minimumInputLength: 1,
//    });

});


