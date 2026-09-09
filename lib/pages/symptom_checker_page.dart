import 'package:flutter/material.dart';
import 'package:identicare_mobile/pages/result_page.dart';
import 'package:identicare_mobile/services/api_service.dart';
import 'package:identicare_mobile/services/verification_api_service.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:provider/provider.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

class SymptomCheckerPage extends StatefulWidget {
  const SymptomCheckerPage({super.key});

  @override
  State<SymptomCheckerPage> createState() => _SymptomCheckerPageState();
}

class _SymptomCheckerPageState extends State<SymptomCheckerPage> {
  final ApiService _apiService = ApiService();
  bool _isLoading = false;

  /// Daftar cadangan kalau server tidak dapat dihubungi. Sumber utamanya
  /// sekarang GET /api/v1/symptoms/catalog, sehingga model AI bisa menambah
  /// atau mengubah gejala tanpa merilis ulang aplikasi.
  List<String> _allSymptoms = [
    'Sakit kepala', 'Pusing', 'Migrain', 'Kehilangan keseimbangan', 'Batuk', 'Sesak Napas', 'Pilek',
    'Nyeri dada saat bernapas', 'Mual', 'Muntah', 'Diare', 'Sakit perut', 'Sembelit',
    'Nafsu makan menurun', 'Detak jantung tidak teratur', 'Nyeri dada', 'Tekanan darah tinggi',
    'Mudah lelah', 'Demam', 'Menggigil', 'Berkeringat berlebihan', 'Tubuh terasa lemas', 'Nyeri otot',
    'Sendi kaku', 'Bengkak', 'Sulit bergerak (sendi/otot)', 'Mata merah', 'Penglihatan kabur',
    'Bengkak (mata)', 'Mata sulit fokus/bergerak normal', 'Sakit tenggorokan', 'Hidung tersumbat',
    'Gangguan pendengaran', 'Sakit telinga', 'Ruam', 'Gatal-gatal', 'Luka tidak sembuh', 'Kulit kering',
    'Stres', 'Cemas', 'Sulit tidur', 'Mudah marah'
  ];

  final Set<String> _selectedSymptoms = {};
  bool _catalogLoaded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadCatalog());
  }

  Future<void> _loadCatalog() async {
    final api = Provider.of<VerificationApiService>(context, listen: false);
    final result = await api.fetchSymptomCatalog();
    if (!mounted) return;
    result.when(
      ok: (gejala) {
        if (gejala.isNotEmpty) {
          setState(() {
            _allSymptoms = gejala;
            _catalogLoaded = true;
          });
        }
      },
      // Bukan kegagalan yang perlu ditampilkan: daftar cadangan tetap dipakai.
      failure: (_) => setState(() => _catalogLoaded = true),
    );
  }

  Future<void> _processSymptoms() async {
    if (_selectedSymptoms.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pilih minimal satu gejala.'), backgroundColor: Colors.orange),
      );
      return;
    }

    setState(() { _isLoading = true; });

    final result = await _apiService.analyzeSymptoms(_selectedSymptoms.toList());
    final user = Provider.of<AuthService>(context, listen: false).currentUser;

    if (mounted && result['status'] == 'ok' && user != null) {
      try {
        await FirebaseFirestore.instance.collection('riwayat_konsultasi').add({
          'userId': user.uid,
          'email': user.email,
          'gejala': _selectedSymptoms.toList(),
          'hasilAI': result['result'],
          'timestamp': FieldValue.serverTimestamp(),
        });
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Gagal menyimpan riwayat: $e'), backgroundColor: Colors.red),
          );
        }
      }
    }

    setState(() { _isLoading = false; });

    if (mounted) {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (context) => ResultPage(analysisResult: result)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Konsultasi Gejala'),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16,0,16,16),
            child: Text(
              'Pilih semua gejala yang Anda rasakan saat ini. Semakin detail, semakin baik analisisnya.',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade700),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: _allSymptoms.length,
              itemBuilder: (context, index) {
                final symptom = _allSymptoms[index];
                return CheckboxListTile(
                  title: Text(symptom),
                  value: _selectedSymptoms.contains(symptom),
                  activeColor: Theme.of(context).colorScheme.primary,
                  onChanged: (bool? value) {
                    setState(() {
                      if (value == true) {
                        _selectedSymptoms.add(symptom);
                      } else {
                        _selectedSymptoms.remove(symptom);
                      }
                    });
                  },
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _processSymptoms,
                      child: const Text('Dapatkan Analisis AI'),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
