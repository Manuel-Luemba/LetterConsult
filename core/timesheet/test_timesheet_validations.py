# tests/test_timesheet_validations.py
import requests
import json
from datetime import date, timedelta
from decimal import Decimal

BASE_URL = "http://127.0.0.1:8000/api/v1"
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY5ODQ4MDU5LCJpYXQiOjE3Njk3NjE2NTksImp0aSI6ImQxMmQ3ZmE4YjhjOTQxYWFiYjY1MmJlYzU5MWMwMzM1IiwidXNlcl9pZCI6IjEifQ.6E_uAuZ1VZ4cR2RvnpeA7FhdSr-Qzf7cfYFq_ALIthA"  # Substitua pelo seu token
}


def print_test(title, result, expected, data=None):
    """Função auxiliar para imprimir resultados de testes"""
    status = "✅ PASSOU" if result == expected else "❌ FALHOU"
    print(f"\n{'=' * 60}")
    print(f"TESTE: {title}")
    print(f"STATUS: {status}")
    if data:
        print(f"DADOS ENVIADOS: {json.dumps(data, indent=2, default=str)}")
    if result != expected:
        print(f"ESPERADO: {expected}")
        print(f"RECEBIDO: {result}")
    print(f"{'=' * 60}")


def test_1_max_daily_hours():
    """Teste 1: Limite de 16h por dia por colaborador"""
    print("\n🧪 TESTE 1: Limite diário de 16h")

    # Criar uma timesheet com 10h no dia 2026-01-30
    timesheet_1 = {
        "employee_id": 1,  # Manuel Luemba
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste limite diário",
        "tasks": [
            {
                "project_id": 3,  # 3feet
                "activity_id": 20,
                "hour": "10.00",
                "created_at": "2026-01-30"
            }
        ],
        "created_at": "2026-01-30",
        "validation_level": "strict"
    }

    # Tentar criar segunda timesheet no mesmo dia com 8h
    timesheet_2 = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste limite diário - segunda",
        "tasks": [
            {
                "project_id": 6,  # l dfkewnk
                "activity_id": 20,
                "hour": "8.00",
                "created_at": "2026-01-30"
            }
        ],
        "created_at": "2026-01-30",
        "validation_level": "strict"
    }

    # Primeira timesheet deve passar
    response_1 = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_1
    )

    if response_1.status_code == 207:
        # Confirmar com force_confirm
        timesheet_1["force_confirm"] = True
        response_1 = requests.post(
            f"{BASE_URL}/timesheets",
            headers=HEADERS,
            json=timesheet_1
        )

    print_test("Primeira timesheet (10h)", response_1.status_code in [200, 207], True, timesheet_1)

    # Segunda timesheet deve FALHAR (10h + 8h = 18h > 16h)
    response_2 = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_2
    )

    print_test("Segunda timesheet (8h) - deve falhar", response_2.status_code, 400, timesheet_2)

    if response_2.status_code == 400:
        print("Mensagem de erro:", response_2.json())

    return response_1.status_code in [200, 207] and response_2.status_code == 400


def test_2_retroactive_limit():
    """Teste 2: Limite de 30 dias para tarefas retroativas"""
    print("\n🧪 TESTE 2: Limite retroativo (30 dias)")

    today = date.today()
    too_old_date = (today - timedelta(days=35)).isoformat()

    timesheet = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste limite retroativo",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "8.00",
                "created_at": too_old_date  # 35 dias atrás
            }
        ],
        "created_at": today.isoformat(),
        "validation_level": "strict"
    }

    response = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet
    )

    print_test("Tarefa muito antiga (35 dias)", response.status_code, 400, timesheet)

    if response.status_code == 400:
        print("Mensagem de erro:", response.json())

    return response.status_code == 400


def test_3_cross_timesheet_duplicate():
    """Teste 3: Evitar tarefa duplicada entre timesheets"""
    print("\n🧪 TESTE 3: Duplicidade entre timesheets")

    # Primeira timesheet com tarefa específica
    timesheet_1 = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste duplicidade - primeira",
        "tasks": [
            {
                "project_id": 7,  # Projeto Alpha
                "activity_id": 20,
                "hour": "4.00",
                "created_at": "2026-01-31"
            }
        ],
        "created_at": "2026-01-31",
        "validation_level": "strict"
    }

    # Segunda timesheet com MESMA tarefa
    timesheet_2 = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste duplicidade - segunda",
        "tasks": [
            {
                "project_id": 7,  # MESMO projeto
                "activity_id": 20,  # MESMA atividade
                "hour": "3.00",
                "created_at": "2026-01-31"  # MESMA data
            }
        ],
        "created_at": "2026-01-31",
        "validation_level": "strict"
    }

    # Criar primeira timesheet
    response_1 = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_1
    )

    print_test("Primeira tarefa (4h)", response_1.status_code in [200, 207], True, timesheet_1)

    # Segunda deve FALHAR por duplicidade
    response_2 = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_2
    )

    print_test("Tarefa duplicada (3h) - deve falhar", response_2.status_code, 400, timesheet_2)

    if response_2.status_code == 400:
        print("Mensagem de erro:", response_2.json())

    return response_1.status_code in [200, 207] and response_2.status_code == 400


def test_4_temporal_consistency():
    """Teste 4: Consistência temporal"""
    print("\n🧪 TESTE 4: Consistência temporal")

    today = date.today()
    future_date = (today + timedelta(days=5)).isoformat()

    # Teste 4A: Tarefa futura
    timesheet_a = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste tarefa futura",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "8.00",
                "created_at": future_date  # Data futura
            }
        ],
        "created_at": today.isoformat(),
        "validation_level": "strict"
    }

    response_a = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_a
    )

    print_test("Tarefa com data futura", response_a.status_code, 400, timesheet_a)

    # Teste 4B: Tarefa posterior à timesheet
    timesheet_b = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste tarefa posterior",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "8.00",
                "created_at": "2026-02-05"  # Depois da timesheet
            }
        ],
        "created_at": "2026-02-01",  # Timesheet antes da tarefa
        "validation_level": "strict"
    }

    response_b = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_b
    )

    print_test("Tarefa posterior à timesheet", response_b.status_code, 400, timesheet_b)

    return response_a.status_code == 400 and response_b.status_code == 400


def test_5_min_task_hours():
    """Teste 5: Mínimo de 0.5h por tarefa"""
    print("\n🧪 TESTE 5: Mínimo de horas por tarefa")

    timesheet = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste mínimo de horas",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "0.25",  # Menos que 0.5h
                "created_at": "2026-02-01"
            }
        ],
        "created_at": "2026-02-01",
        "validation_level": "strict"
    }

    response = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet
    )

    print_test("Tarefa com 0.25h (menos que mínimo)", response.status_code, 400, timesheet)

    if response.status_code == 400:
        print("Mensagem de erro:", response.json())

    return response.status_code == 400


def test_6_validation_preview():
    """Teste 6: Endpoint de validação preview"""
    print("\n🧪 TESTE 6: Validação preview (sem criar)")

    timesheet_data = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste preview",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "10.00",
                "created_at": "2026-02-02"
            },
            {
                "project_id": 7,
                "activity_id": 20,
                "hour": "6.00",
                "created_at": "2026-02-02"  # Total: 16h
            }
        ],
        "created_at": "2026-02-02",
        "validation_level": "strict"
    }

    response = requests.post(
        f"{BASE_URL}/timesheets/validate",
        headers=HEADERS,
        json=timesheet_data
    )

    if response.status_code == 200:
        data = response.json()
        print_test("Validação preview", True, True, timesheet_data)
        print("Resposta da validação:")
        print(json.dumps(data, indent=2, default=str))

        # Verificar se mostra total agregado correto
        aggregated = data.get("aggregated_totals", {})
        if "2026-02-02" in aggregated:
            total = aggregated["2026-02-02"]
            print(f"Total agregado no dia: {total}h")

        return True
    else:
        print_test("Validação preview", False, True, timesheet_data)
        print("Erro:", response.json())
        return False


def test_7_warning_system():
    """Teste 7: Sistema de warnings"""
    print("\n🧪 TESTE 7: Sistema de warnings")

    # Teste 7A: Warning para >8h
    timesheet_a = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste warning >8h",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "9.00",  # >8h - deve dar warning
                "created_at": "2026-02-03"
            }
        ],
        "created_at": "2026-02-03",
        "validation_level": "strict"
    }

    response_a = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_a
    )

    if response_a.status_code == 207:
        print_test("Warning para tarefa >8h", True, True, timesheet_a)
        print("Warnings recebidos:", response_a.json()["warnings"])
    else:
        print_test("Warning para tarefa >8h", False, True, timesheet_a)

    # Teste 7B: Warning para <8h diárias
    timesheet_b = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste warning <8h diárias",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "4.00",  # <8h diárias - deve dar warning
                "created_at": "2026-02-04"
            }
        ],
        "created_at": "2026-02-04",
        "validation_level": "strict"
    }

    response_b = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet_b
    )

    if response_b.status_code == 207:
        print_test("Warning para <8h diárias", True, True, timesheet_b)
        print("Warnings recebidos:", response_b.json()["warnings"])
    else:
        print_test("Warning para <8h diárias", False, True, timesheet_b)

    return response_a.status_code == 207 and response_b.status_code == 207


def test_8_force_confirm():
    """Teste 8: Force confirm ignora warnings"""
    print("\n🧪 TESTE 8: Force confirm")

    timesheet = {
        "employee_id": 1,
        "department_id": 2,
        "status": "rascunho",
        "obs": "Teste force confirm",
        "tasks": [
            {
                "project_id": 3,
                "activity_id": 20,
                "hour": "9.00",  # >8h - normalmente daria warning
                "created_at": "2026-02-05"
            }
        ],
        "created_at": "2026-02-05",
        "validation_level": "strict",
        "force_confirm": True  # Ignora warnings
    }

    response = requests.post(
        f"{BASE_URL}/timesheets",
        headers=HEADERS,
        json=timesheet
    )

    # Com force_confirm, deve criar sem warning (status 200)
    print_test("Force confirm ignora warnings", response.status_code, 200, timesheet)

    return response.status_code == 200


def cleanup_test_data():
    """Limpa dados de teste (opcional)"""
    print("\n🧹 Limpando dados de teste...")

    # Listar timesheets de teste
    response = requests.get(
        f"{BASE_URL}/timesheets/all?page=1&page_size=100&employee_id=1",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        for timesheet in data.get("items", []):
            if "Teste" in timesheet.get("obs", ""):
                print(f"Deletando timesheet {timesheet['id']}: {timesheet['obs']}")
                # Só pode deletar se for rascunho
                if timesheet["status"] == "Rascunho":
                    delete_response = requests.delete(
                        f"{BASE_URL}/timesheets/{timesheet['id']}",
                        headers=HEADERS
                    )
                    if delete_response.status_code == 200:
                        print(f"✅ Deletado: {timesheet['id']}")
                    else:
                        print(f"❌ Erro ao deletar {timesheet['id']}: {delete_response.json()}")


def run_all_tests():
    """Executa todos os testes"""
    print("🚀 INICIANDO TESTES DAS NOVAS VALIDAÇÕES")
    print("=" * 60)

    results = []

    try:
        # Testar conexão
        print("🔗 Testando conexão com API...")
        test_response = requests.get(f"{BASE_URL}/timesheets/my", headers=HEADERS)
        if test_response.status_code != 200:
            print("❌ Não consegui conectar à API. Verifique:")
            print(f"   - URL: {BASE_URL}")
            print(
                f"   - Token: {'Válido' if 'SEU_TOKEN_AQUI' not in HEADERS['Authorization'] else 'INVÁLIDO - substitua'}")
            print(f"   - Resposta: {test_response.status_code}")
            return False

        print("✅ Conexão OK!")

        # Executar testes
        results.append(("1. Limite diário 16h", test_1_max_daily_hours()))
        results.append(("2. Limite retroativo", test_2_retroactive_limit()))
        results.append(("3. Duplicidade entre timesheets", test_3_cross_timesheet_duplicate()))
        results.append(("4. Consistência temporal", test_4_temporal_consistency()))
        results.append(("5. Mínimo 0.5h por tarefa", test_5_min_task_hours()))
        results.append(("6. Validação preview", test_6_validation_preview()))
        results.append(("7. Sistema de warnings", test_7_warning_system()))
        results.append(("8. Force confirm", test_8_force_confirm()))

        # Resumo
        print("\n" + "=" * 60)
        print("📊 RESUMO DOS TESTES")
        print("=" * 60)

        passed = 0
        for name, result in results:
            status = "✅ PASSOU" if result else "❌ FALHOU"
            print(f"{name}: {status}")
            if result:
                passed += 1

        print(f"\n🎯 Total: {passed}/{len(results)} testes passaram")

        # Limpar dados de teste
        cleanup_test_data()

        return passed == len(results)

    except requests.exceptions.ConnectionError:
        print("❌ Erro de conexão. Verifique se o servidor Django está rodando.")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False


if __name__ == "__main__":
    # ANTES DE EXECUTAR:
    print("⚠️  INSTRUÇÕES:")
    print("1. Substitua 'SEU_TOKEN_AQUI' pelo seu token JWT válido")
    print("2. Certifique-se que o servidor Django está rodando")
    print("3. Use datas futuras para não interferir com dados reais")
    print("\nPressione Enter para continuar...")
    input()

    # Executar testes
    success = run_all_tests()

    if success:
        print("\n🎉 TODOS OS TESTES PASSARAM! As validações estão funcionando corretamente.")
    else:
        print("\n⚠️  Alguns testes falharam. Verifique os logs acima.")