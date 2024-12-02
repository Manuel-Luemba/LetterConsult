$(function () {
    $('#groups').select2({
        theme: "bootstrap4",
        language: 'pt',
        placeholder:'Selecione os grupos'
    });

    $('#position').select2({
        theme: "bootstrap4",
        language: 'pt',
        placeholder:'Selecione o cargo'
    });

    $('#department').select2({
        theme: "bootstrap4",
        language: 'pt',
        placeholder:'Selecione o departamento'
    });


const action = document.getElementById('action').value;
console.log(action)
if(action === 'add'){
    $("#email").keyup(function() {
        // Seu código aqui
        let email = this.value;
        var username= "";
        // Verifique se há um "@" no valor
        let posicaoArroba = email.indexOf("@");
        console.log(posicaoArroba)
        if (posicaoArroba !== -1) {
            // Se houver um "@", pegue a parte antes dele
            let parteAntesDoArroba = email.substring(0, posicaoArroba);
            console.log(parteAntesDoArroba, 'ddd')
            username = parteAntesDoArroba;
        } else {
            // Caso contrário, apenas copie o valor do campo1 para o campo2
            username = email;
        }
        $("#username").val(username);
        // Execute outras ações conforme necessário
});
    }



});