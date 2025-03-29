// src/routes/packageRoutes.ts
import Router from '@koa/router';
import multer from '@koa/multer';
import { PackageController } from '../controllers/packageController';
import { authenticate } from '../middlewares/auth';
import { Db } from 'mongodb';

export function packageRoutes(db: Db): Router {
  const router = new Router({
    prefix: '/api/packages'
  });
  const packageController = new PackageController(db);

  // 使用 koa-multer 读取上传的文件到内存
  const upload = multer();

  // 发布包（需要 API Key 验证）
  router.post(
    '/publish',
    authenticate(db),
    upload.single('file'),
    async (ctx) => {
      await packageController.publish(ctx);
    }
  );

  // 删除包（需要 API Key 验证）
  router.delete('/:packageName', authenticate(db), async (ctx) => {
    await packageController.deletePackage(ctx);
  });

  // 下载包（无需认证）
  router.get('/:packageName/download/:version', async (ctx) => {
    await packageController.download(ctx);
  });

  // 搜索包
  router.get('/search', async (ctx) => {
    await packageController.searchPackages(ctx);
  });

  // 获取最新版本号
  router.get('/:packageName/ver', async (ctx) => {
    await packageController.getLatestVersion(ctx);
  });

  return router;
}