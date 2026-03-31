function validaCPF(value,inputField,div,divMsg)  
{
	strCPF = value.replace(/[^\d]+/g,'');
    var Soma;
    var Resto;
    Soma = 0;
	if (strCPF == "00000000000")
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "CPF inválido.";
		//document.getElementById(inputField).focus();
		return false;
	}
    
	for (i=1; i<=9; i++) Soma = Soma + parseInt(strCPF.substring(i-1, i)) * (11 - i);
	Resto = (Soma * 10) % 11;
	
    if ((Resto == 10) || (Resto == 11))  Resto = 0;
    if (Resto != parseInt(strCPF.substring(9, 10)) ) 
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "CPF inválido.";
		//document.getElementById(inputField).focus();
		return false;
	}
	
	Soma = 0;
    for (i = 1; i <= 10; i++) Soma = Soma + parseInt(strCPF.substring(i-1, i)) * (12 - i);
    Resto = (Soma * 10) % 11;
	
    if ((Resto == 10) || (Resto == 11))  Resto = 0;
    if (Resto != parseInt(strCPF.substring(10, 11) ) )
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "CPF inválido.";
		//document.getElementById(inputField).focus();
		return false;
	}
	
	document.getElementById(div).style.display = "none";
	document.getElementById(divMsg).innerHTML = ""; 
    return true;
}

function FormataData(obj)
{

	if (obj.value.length == 2 && ut !=10)
	obj.value += "/";
	if (obj.value.length == 5 && ut !=10)
	obj.value += "/";

}

function validaCheck(inputField,div,divMsg)
{
	var atributo = document.getElementById(inputField);
	if(atributo.checked==false)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = atributo.dataset.msgRequired; 
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = ""; 
		return true;
	}
}

function validaCNPJ(value,inputField,div,divMsg) 
{
 
    cnpj = value.replace(/[^\d]+/g,'');
 
    if(cnpj == '') 
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Campo CNPJ é obrigatório.";
		//document.getElementById(inputField).focus();
		return false;
	}
     
    if (cnpj.length != 14)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Tamanho do CNPJ é inválido.";
		//document.getElementById(inputField).focus();
        return false;
	}
    // Elimina CNPJs invalidos conhecidos
    if (cnpj == "00000000000000" || 
        cnpj == "11111111111111" || 
        cnpj == "22222222222222" || 
        cnpj == "33333333333333" || 
        cnpj == "44444444444444" || 
        cnpj == "55555555555555" || 
        cnpj == "66666666666666" || 
        cnpj == "77777777777777" || 
        cnpj == "88888888888888" || 
        cnpj == "99999999999999")
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "CNPJ é inválido.";
		//document.getElementById(inputField).focus(); 
        return false;
	}
    // Valida DVs
    tamanho = cnpj.length - 2
    numeros = cnpj.substring(0,tamanho);
    digitos = cnpj.substring(tamanho);
    soma = 0;
    pos = tamanho - 7;
    for (i = tamanho; i >= 1; i--) {
      soma += numeros.charAt(tamanho - i) * pos--;
      if (pos < 2)
            pos = 9;
    }
    resultado = soma % 11 < 2 ? 0 : 11 - soma % 11;
    if (resultado != digitos.charAt(0))
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Dígito verificador inválido.";
		//document.getElementById(inputField).focus();
        return false;
	}
         
    tamanho = tamanho + 1;
    numeros = cnpj.substring(0,tamanho);
    soma = 0;
    pos = tamanho - 7;
    for (i = tamanho; i >= 1; i--) {
      soma += numeros.charAt(tamanho - i) * pos--;
      if (pos < 2)
            pos = 9;
    }
    resultado = soma % 11 < 2 ? 0 : 11 - soma % 11;
    if (resultado != digitos.charAt(1))
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "CNPJ é inválido.";
		//document.getElementById(inputField).focus();
        return false;
	}
	
   	document.getElementById(div).style.display = "none";
	document.getElementById(divMsg).innerHTML = ""; 
	//document.getElementById(inputField).focus();
    return true;
    
}

function validaArquivo(inputField,div,divMsg)
{
	var atributo = document.getElementById(inputField);
	var extensoesPermitidas = /(.xlsx|.xls|.pdf|.docx|.doc|.jpg|.png|.gif|.csv|.jpeg)$/i;
	
	if (atributo.files[0]) 
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = "";
		
		if(!extensoesPermitidas.exec(atributo.files[0].name))
		{
			document.getElementById(div).style.display = "block";
			document.getElementById(divMsg).innerHTML = "Extensão de arquivo inválida. Somente é permitido as extensões: .xlsx, .xls, .pdf, .docx, .doc, .jpg, .png, .gif e .csv. ";  
			return false;
		} 
		else
		{
		 	document.getElementById(div).style.display = "none";
			document.getElementById(divMsg).innerHTML = "";
			
			
			if (atributo.files[0].size > 2097152) 
			{
				document.getElementById(div).style.display = "block";
				document.getElementById(divMsg).innerHTML = "O tamanho do arquivo não pode exceder a 2MB!";  
				return false;
			} 
			else 
			{
			 	document.getElementById(div).style.display = "none";
				document.getElementById(divMsg).innerHTML = "";
				return true;
			}
		}	
	} 
	else 
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Por favor, selecione o Arquivo"; 
		return false;
	}	
}

function validaNull(value,inputField,div,divMsg)
{
	var atributo = document.getElementById(inputField);
	var valor = value.trim();
	
	if(valor=='')
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = atributo.dataset.msgRequired; 
		document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = ""; 
		return true;
	}
	
}

function validaSelectNull(value,inputField,div,divMsg)
{
	var atributo = document.getElementById(inputField).selectedIndex;
	var valor = value.trim();

	if((valor=='')||(valor==0))
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = atributo.dataset.msgRequired; 
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = ""; 
		return true;
	}
	
}

function validaSenha(value,inputField,div,divMsg)
{
	var valor = value.trim();
	
	if(valor=='')
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Por favor, informe uma senha para acessar Jolie Wines.";
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else if(valor.length<8)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "A senha deve conter pelo menos 8 caracteres.";
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = ""; 
		return true;
	}
	
}

function comparaSenha(value,valueBase,inputField,div,divMsg)
{
	var valor = value.trim();
	var valorBase = document.getElementById(valueBase).value;
	var valorBase = valorBase.trim();
	

	
	if(valor=='')
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "Por favor, Repita a senha.";
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else if(valor.length<8)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "A senha deve conter pelo menos 8 caracteres.";
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else if(valorBase!=valor)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "As senhas informadas são diferentes.";
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = ""; 
		return true;
	}
	
}

function validaEmail(value,inputField,div,divMsg)
{
	//testa se endereço de email é válido.
	var checkEmail = "@.";
	var checkStr = value;
	var EmailValid = false;
	var EmailAt = false;
	var EmailPeriod = false;

	for (i = 0;  i < checkStr.length;  i++){
		ch = checkStr.charAt(i);
		for (j = 0;  j < checkEmail.length;  j++){
			
			if (ch == checkEmail.charAt(j) && ch == "@")
				EmailAt = true;
					
			if (ch == checkEmail.charAt(j) && ch == ".")
				EmailPeriod = true;			
				
			if (EmailAt && EmailPeriod)
				break;
				
			if (j == checkEmail.length)	
				break;
		}
	 
		// verifica se há @ e . no endereço
		if (EmailAt && EmailPeriod)
		{
			EmailValid = true
			break;
		}
	}
	 
	if (!EmailValid)
	{
		document.getElementById(div).style.display = "block";
		document.getElementById(divMsg).innerHTML = "E-mail Inválido"; 
		//document.getElementById(inputField).focus(); 
		return false;
	}
	else
	{
		document.getElementById(div).style.display = "none";
		document.getElementById(divMsg).innerHTML = "";
		return true;
	}
}



// máscara de campos
// uso: onkeydown="FormataCampo(this,event,'##/##/####')"
function FormataCampo(Campo,teclapres,mascara, sai) {

	if (sai == "S" && consistente == "N") {
		if (obrigatorio == "N" && Campo.value.length > 0) {
			obrig_fixo = "S";
			Consist(Campo.maxLength, Campo);
			obrig_fixo = "N";
		}
		if (obrigatorio == "S" || Campo.value.length > 0) {
			if (sai == "S") {
				if (Campo.value.length != mascara.length) {
					alert('O campo precisa estar neste formato:\n\n       '+ mascara);
					Campo.value = "";
				}
				erro = "S";
				return false;
			}
		}
	}
	if (sai == "S" && obrigatorio == "N" && Campo.value.length > 0) {
		obrig_fixo = "S";
		Consist(Campo.maxLength, Campo);
		obrig_fixo = "N";
		if (consistente == "N") {
			alert('O campo precisa estar neste formato:\n\n       '+ mascara);
		}
	}


	strtext = Campo.value;
	tamtext = strtext.length;
	tammask = mascara.length;
	arrmask = new Array(tammask);
	for (var i = 0 ; i < tammask; i++) {
		arrmask[i] = mascara.slice(i,i+1)
	} 

	//alert(teclapres.keyCode );
	if (((((arrmask[tamtext] == "#") || (arrmask[tamtext] == "9"))) || (((arrmask[tamtext+1] != "#") || (arrmask[tamtext+1] != "9"))))) {
		if ((teclapres.keyCode >= 35 && teclapres.keyCode <= 40)||(teclapres.keyCode >= 48 && teclapres.keyCode <= 57)||(teclapres.keyCode >= 96 && teclapres.keyCode <= 105)||(teclapres.keyCode == 8)||(teclapres.keyCode == 9) ||(teclapres.keyCode == 46) ||(teclapres.keyCode == 13)||(teclapres.keyCode == 16)){
			Organiza_Casa(Campo,arrmask[tamtext],teclapres.keyCode,strtext)		
		} else {
			Detona_Event(Campo,strtext)
		}
	} else {
		if ((arrmask[tamtext] == "A")) {
			charupper = event.valueOf()
			Detona_Event(Campo,strtext)
			masktext = strtext + charupper 
			Campo.value = masktext
		}
	}
}

function Organiza_Casa(Campo,arrpos,teclapres_key,strtext)
{
	if (((arrpos == "/") || (arrpos == ".") || (arrpos == ",") || (arrpos == ":") || (arrpos == " ") || (arrpos == "-")) && !(teclapres_key == 8))
	{
		separador = arrpos
		masktext = strtext + separador
		Campo.value = masktext
	}
}

function Detona_Event(Campo,strtext)
{
	event.returnValue = false
	if (strtext != "") 
	{
		Campo.value = strtext
	}
}

//Aplica a máscara no campo
//Função para ser utilizada nos eventos do input para formatação dinâmica
function aplica_mascara_cpfcnpj(campo,tammax,teclapres) {
	var tecla = teclapres.keyCode;
	
	if ((tecla < 48 || tecla > 57) && (tecla < 96 || tecla > 105) && tecla != 46 && tecla != 8 && tecla != 9) {
		return false;
	}

	var vr = campo.value;
	vr = vr.replace( /\//g, "" );
	vr = vr.replace( /-/g, "" );
	vr = vr.replace( /\./g, "" );
	var tam = vr.length;

	if ( tam <= 2 ) {
		campo.value = vr;
	}
	if ( (tam > 2) && (tam <= 5) ) {
		campo.value = vr.substr( 0, tam - 2 ) + '-' + vr.substr( tam - 2, tam );
	}
	if ( (tam >= 6) && (tam <= 8) ) {
		campo.value = vr.substr( 0, tam - 5 ) + '.' + vr.substr( tam - 5, 3 ) + '-' + vr.substr( tam - 2, tam );
	}
	if ( (tam >= 9) && (tam <= 11) ) {
		campo.value = vr.substr( 0, tam - 8 ) + '.' + vr.substr( tam - 8, 3 ) + '.' + vr.substr( tam - 5, 3 ) + '-' + vr.substr( tam - 2, tam );
	}
	if ( (tam == 12) ) {
		campo.value = vr.substr( tam - 12, 3 ) + '.' + vr.substr( tam - 9, 3 ) + '/' + vr.substr( tam - 6, 4 ) + '-' + vr.substr( tam - 2, tam );
	}
	if ( (tam > 12) && (tam <= 14) ) {
		campo.value = vr.substr( 0, tam - 12 ) + '.' + vr.substr( tam - 12, 3 ) + '.' + vr.substr( tam - 9, 3 ) + '/' + vr.substr( tam - 6, 4 ) + '-' + vr.substr( tam - 2, tam );
	}
}

function verifica_cpf_cnpj(value,inputField,div) 
{
	if (value.length == 14) 
	{
		document.getElementById('hdTipoPessoa').value = 'pf';
		return(validaCPF(value,inputField,div));
	} 
	else if (value.length == 18) 
	{
		document.getElementById('hdTipoPessoa').value = 'pj';
		return(validaCNPJ(value,inputField,div));
	} 
	else 
	{ 
		document.getElementById(div).style.display = "block";
		document.getElementById(div).innerHTML = "Verifique o valor digitado."; 
		document.getElementById(inputField).className = document.getElementById(inputField).className + " error"; 
		return false;
	}
	return true;
}

//Verifica se o número de CPF informado é válido
function verifica_cpf(sequencia) {
	if ( Procura_Str(1,sequencia,'00000000000,11111111111,22222222222,33333333333,44444444444,55555555555,66666666666,77777777777,88888888888,99999999999,00000000191,19100000000') > 0 ) {
		return false;
	}
	seq = sequencia;
	soma = 0;
	multiplicador = 2;
	for (f = seq.length - 3;f >= 0;f--) {
		soma += seq.substring(f,f + 1) * multiplicador;
		multiplicador++;
	}
	resto = soma % 11;
	if (resto == 1 || resto == 0) {
		digito = 0;
	} else {
		digito = 11 - resto;
	}
	if (digito != seq.substring(seq.length - 2,seq.length - 1)) {
		return false;
	}
	soma = 0;
	multiplicador = 2;
	for (f = seq.length - 2;f >= 0;f--) {
		soma += seq.substring(f,f + 1) * multiplicador;
		multiplicador++;
	}
	resto = soma % 11;
	if (resto == 1 || resto == 0) {
		digito = 0;
	} else {
		digito = 11 - resto;
	}
	if (digito != seq.substring(seq.length - 1,seq.length)) {
		return false;
	}
	return true;
}

//Verifica se o número de CNPJ informado é válido
function verifica_cnpj(sequencia) {
	seq = sequencia;
	soma = 0;
	multiplicador = 2;
	for (f = seq.length - 3;f >= 0;f-- ) {
		soma += seq.substring(f,f + 1) * multiplicador;
		if ( multiplicador < 9 ) {
			multiplicador++;
		} else {
			multiplicador = 2;
		}
	}
	resto = soma % 11;
	if (resto == 1 || resto == 0) {
		digito = 0;
	} else {
		digito = 11 - resto;
	}
	if (digito != seq.substring(seq.length - 2,seq.length - 1)) {
		return false;
	}

	soma = 0;
	multiplicador = 2;
	for (f = seq.length - 2;f >= 0;f--) {
		soma += seq.substring(f,f + 1) * multiplicador;
		if (multiplicador < 9) {
			multiplicador++;
		} else {
			multiplicador = 2;
		}
	}
	resto = soma % 11;
	if (resto == 1 || resto == 0) {
		digito = 0;
	} else {
		digito = 11 - resto;
	}
	if (digito != seq.substring(seq.length - 1,seq.length)) {
		return false;
	}
	return true;
}

//Procura uma string dentro de outra string
function Procura_Str(param0,param1,param2) {
	for (a = param0 - 1;a < param1.length;a++) {
		for (b = 1;b < param1.length;b++) {
			if (param2 == param1.substring(b - 1,b + param2.length - 1)) {
				return a;
			}
		}
	}
	return 0;
}

//Retira a máscara do valor de cpf_cnpj
function retira_mascara(cpf_cnpj) {
	return cpf_cnpj.replace(/\./g,'').replace(/-/g,'').replace(/\//g,'')
}