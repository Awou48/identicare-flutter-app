import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class HospitalInfoPage extends StatelessWidget {
  const HospitalInfoPage({super.key});

  Future<void> _launchURL(String url) async {
    final Uri uri = Uri.parse(url);
    if (!await launchUrl(uri)) {
      throw Exception('Could not launch $url');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 250.0,
            pinned: true,
            stretch: true,
            flexibleSpace: FlexibleSpaceBar(
              titlePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              title: const Text(
                'RS IdentiCare Sehat',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  shadows: [Shadow(blurRadius: 10, color: Colors.black54)],
                ),
              ),
              background: Image.network(
                'https://images.unsplash.com/photo-1586773860418-d37222d8fce3?q=80&w=2073&auto=format&fit=crop',
                fit: BoxFit.cover,
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.all(16.0),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _buildSectionTitle(context, 'Informasi Utama'),
                const SizedBox(height: 16),
                _buildInfoCard(
                  context,
                  icon: Icons.location_on_outlined,
                  title: 'Alamat',
                  subtitle: 'Jl. Kesehatan No. 123, Jakarta Sehat, Indonesia',
                  actionWidget: OutlinedButton(
                    onPressed: () => _launchURL('https://maps.google.com/?q=Jl. Kesehatan No. 123, Jakarta'),
                    child: const Text('Lihat Peta'),
                  ),
                ),
                const SizedBox(height: 12),
                _buildInfoCard(
                  context,
                  icon: Icons.phone_in_talk_outlined,
                  title: 'Telepon Gawat Darurat',
                  subtitle: '(021) 123-4567',
                  actionWidget: ElevatedButton(
                    onPressed: () => _launchURL('tel:0211234567'),
                    child: const Text('Panggil'),
                  ),
                ),
                const SizedBox(height: 12),
                _buildInfoCard(
                  context,
                  icon: Icons.access_time_filled_outlined,
                  title: 'Jam Operasional',
                  subtitle: '24 Jam, 7 Hari Seminggu',
                ),
                const SizedBox(height: 32),
                _buildSectionTitle(context, 'Fasilitas Unggulan'),
                const SizedBox(height: 16),
                _buildFacilitiesGrid(),
                const SizedBox(height: 32),
                _buildSectionTitle(context, 'Poli Tersedia'),
                const SizedBox(height: 16),
                _buildPoliChips(),
                 const SizedBox(height: 32),
                _buildSectionTitle(context, 'Jam Kunjungan Pasien'),
                 const SizedBox(height: 16),
                 _buildInfoCard(
                  context,
                  icon: Icons.family_restroom_outlined,
                  title: 'Pagi',
                  subtitle: '11:00 - 13:00 WIB',
                ),
                 const SizedBox(height: 12),
                 _buildInfoCard(
                  context,
                  icon: Icons.nightlife_outlined,
                  title: 'Sore',
                  subtitle: '17:00 - 19:00 WIB',
                ),
              ]),
            ),
          )
        ],
      ),
    );
  }

  Widget _buildSectionTitle(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: Colors.black87,
          ),
    );
  }

  Widget _buildInfoCard(BuildContext context, {required IconData icon, required String title, required String subtitle, Widget? actionWidget}) {
    return Card(
      elevation: 2,
      shadowColor: Colors.grey.withOpacity(0.1),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary, size: 32),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                  const SizedBox(height: 4),
                  Text(subtitle, style: TextStyle(color: Colors.grey.shade700, fontSize: 15)),
                ],
              ),
            ),
            if (actionWidget != null) ...[
              const SizedBox(width: 8),
              actionWidget,
            ]
          ],
        ),
      ),
    );
  }
  
  Widget _buildFacilitiesGrid() {
    final facilities = [
      {'name': 'IGD 24 Jam', 'icon': Icons.emergency_outlined},
      {'name': 'Rawat Inap', 'icon': Icons.king_bed_outlined},
      {'name': 'Laboratorium', 'icon': Icons.science_outlined},
      {'name': 'Radiologi', 'icon': Icons.document_scanner_outlined},
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 2.5,
      ),
      itemCount: facilities.length,
      itemBuilder: (context, index) {
        return Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.grey.shade200),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(facilities[index]['icon'] as IconData, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 8),
              Flexible(child: Text(facilities[index]['name'] as String, style: const TextStyle(fontWeight: FontWeight.w600))),
            ],
          ),
        );
      },
    );
  }

  Widget _buildPoliChips() {
    final poliList = ['Umum', 'Gigi', 'Jantung', 'Anak', 'Kulit', 'Mata', 'THT'];
    return Wrap(
      spacing: 8.0,
      runSpacing: 8.0,
      children: poliList.map((poli) => Chip(
        label: Text(poli),
        backgroundColor: Colors.blue.shade50,
        labelStyle: TextStyle(color: Colors.blue.shade800, fontWeight: FontWeight.w600),
        side: BorderSide(color: Colors.blue.shade100),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      )).toList(),
    );
  }
}
